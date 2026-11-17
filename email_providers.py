"""IMAP/SMTP accounts with lazy UID paging and verified TLS."""
import base64
import email.policy
import hashlib
import imaplib
import json
import os
import re
import smtplib
import ssl
from email.parser import BytesParser
from email.utils import parsedate_to_datetime, formatdate, make_msgid
from pathlib import Path

PROVIDERS = json.loads((Path(__file__).parent / 'static/email-providers.json').read_text())
PROVIDERS_BY_KEY = {provider['key']: provider for provider in PROVIDERS}


def tls_context():
    context=ssl.create_default_context()
    if cafile:=os.environ.get('CENTROMAIL_MAIL_CA_FILE'):
        context.load_verify_locations(cafile=cafile)
    return context


def validate_host(host):
    try:
        host = host.strip().encode('idna').decode('ascii')
    except (UnicodeError, AttributeError):
        raise ValueError('Enter a valid mail server hostname.') from None
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', host):
        raise ValueError('Enter a hostname without a URL, credentials, or path.')
    return host


def imap_connect(config):
    context = tls_context()
    if config['imap_security'] == 'ssl':
        client = imaplib.IMAP4_SSL(config['imap_host'], int(config['imap_port']), ssl_context=context, timeout=15)
    else:
        client = imaplib.IMAP4(config['imap_host'], int(config['imap_port']), timeout=15)
        try:
            client.starttls(ssl_context=context)
        except Exception:
            client.shutdown(); raise
    try:
        client.login(config.get('imap_username') or config['email'], config['password'])
    except Exception:
        client.shutdown(); raise
    return client


def smtp_connect(config):
    context = tls_context()
    if config['smtp_security'] == 'ssl':
        client = smtplib.SMTP_SSL(config['smtp_host'], int(config['smtp_port']), context=context, timeout=15)
    else:
        client = smtplib.SMTP(config['smtp_host'], int(config['smtp_port']), timeout=15)
        try:
            client.ehlo(); client.starttls(context=context); client.ehlo()
        except Exception:
            client.close(); raise
    try:
        client.login(config.get('smtp_username') or config['email'], config.get('smtp_password') or config['password'])
    except Exception:
        client.close(); raise
    return client


def check(status, message):
    if status != 'OK':
        raise RuntimeError(message)


def discover_folders(client):
    status, rows = client.list()
    check(status, 'The server could not list mail folders.')
    folders = {'inbox':'INBOX'}
    flags = {'\\sent':'sent','\\drafts':'drafts','\\trash':'trash','\\junk':'spam','\\all':'all','\\archive':'archive'}
    aliases = {'sent':'sent','sent items':'sent','sent messages':'sent','drafts':'drafts','trash':'trash','deleted items':'trash','junk':'spam','spam':'spam','archive':'archive','archives':'archive'}
    for row in rows or []:
        if not isinstance(row, bytes): continue
        match = re.match(rb'\((.*?)\) (?:"[^"]*"|NIL) (.+)', row)
        if not match: continue
        name = match[2].decode('ascii',errors='replace').strip('"').replace('\\"','"').replace('\\\\','\\')
        if '\r' in name or '\n' in name: continue
        special = next((flags[flag.lower()] for flag in match[1].decode().split() if flag.lower() in flags),None)
        special = special or aliases.get(name.lower())
        if special: folders[special] = name
    return folders


def mailbox_name(config, folder):
    folder = 'inbox' if folder == 'starred' else folder
    name = config['folders'].get(folder)
    if not name: raise RuntimeError('This account does not have that folder.')
    return '"' + name.replace('\\','\\\\').replace('"','\\"') + '"'


def select_folder(client, config, folder, readonly=True):
    status, _ = client.select(mailbox_name(config, folder), readonly=readonly)
    check(status, 'The mail folder could not be opened.')
    _, validity = client.response('UIDVALIDITY')
    return (validity or [b'0'])[0].decode()


def message_payload(raw, flags, message_id, folder):
    message = BytesParser(policy=email.policy.default).parsebytes(raw)
    try:
        when = parsedate_to_datetime(str(message.get('Date','')))
        timestamp = int(when.timestamp()*1000)
    except (TypeError,ValueError,OverflowError): timestamp = 0
    labels = ['STARRED'] if b'\\Flagged' in flags else []
    if b'\\Seen' not in flags: labels.append('UNREAD')
    if folder in {'inbox','starred'}: labels.append('INBOX')
    if folder == 'sent': labels.append('SENT')
    if folder == 'drafts': labels.append('DRAFT')
    if folder == 'trash': labels.append('TRASH')
    if folder == 'spam': labels.append('SPAM')
    return {'id':message_id,'labelIds':labels,'internalDate':str(timestamp),'snippet':'',
        'payload':{'headers':[{'name':name,'value':str(message.get(name,''))} for name in ('From','Subject','Date','Reply-To','To','Message-ID','References','In-Reply-To')]}}


def list_messages(config, cursor='', query='', folder='inbox', limit=25):
    if '\r' in query or '\n' in query: raise ValueError('Mail searches cannot contain new lines.')
    with imap_connect(config) as client:
        validity = select_folder(client, config, folder)
        criteria = ['UNDELETED']
        if folder == 'starred': criteria.append('FLAGGED')
        if query:
            # UTF-8 search values are sent as quoted bytes, never IMAP syntax.
            quoted = ('"'+query.replace('\\','\\\\').replace('"','\\"')+'"').encode('utf-8')
            criteria += ['TEXT',quoted]
        status, result = client.uid('SEARCH', 'CHARSET', 'UTF-8', *criteria) if query else client.uid('SEARCH',None,*criteria)
        check(status,'The server could not search this folder.')
        ids = sorted((int(uid) for uid in (result[0] or b'').split()),reverse=True)
        total = len(ids)
        if cursor:
            if not cursor.isdigit(): raise ValueError('Invalid mail page.')
            ids = [uid for uid in ids if uid < int(cursor)]
        selected = ids[:limit]
        if not selected: return [],None,total
        status, rows = client.uid('FETCH',','.join(map(str,selected)), '(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE REPLY-TO TO MESSAGE-ID REFERENCES IN-REPLY-TO)])')
        check(status,'The server could not read mail headers.')
        messages={}
        for row in rows or []:
            if not isinstance(row,tuple): continue
            header,raw=row
            uid=re.search(rb'UID (\d+)',header)
            if not uid: continue
            number=int(uid[1]); message_id=make_id(config,folder,validity,number)
            messages[number]=message_payload(raw,header,message_id,folder)
        return [messages[uid] for uid in selected if uid in messages], str(selected[-1]) if len(ids)>limit else None,total


def folder_id(config,folder):
    return hashlib.sha256(mailbox_name(config,folder).encode()).hexdigest()[:12]


def make_id(config,folder,validity,uid):
    return f"imap-{config['account_id']}-{folder_id(config,folder)}-{validity}-{uid}"


def parse_id(config,message_id,validity=None,folder='inbox'):
    match=re.fullmatch(r'imap-([a-f0-9]{12})-([a-f0-9]{12})-(\d+)-(\d+)',message_id)
    if not match or match[1] != config['account_id'] or match[2] != folder_id(config,folder) or (validity is not None and match[3] != validity):
        raise ValueError('This message no longer belongs to the selected mailbox. Refresh and try again.')
    return match[4]


def mime_payload(message):
    if message.is_multipart(): return {'mimeType':message.get_content_type(),'parts':[mime_payload(part) for part in message.iter_parts()]}
    data=message.get_payload(decode=True) or b''
    if message.get_content_maintype()=='text':
        try: data=data.decode(message.get_content_charset() or 'utf-8',errors='replace').encode()
        except LookupError: data=data.decode('utf-8',errors='replace').encode()
    return {'mimeType':message.get_content_type(),'body':{'data':base64.urlsafe_b64encode(data).decode()}}


def read_message(config,message_id,folder='inbox'):
    with imap_connect(config) as client:
        validity=select_folder(client,config,folder)
        uid=parse_id(config,message_id,validity,folder)
        status,rows=client.uid('FETCH',uid,'(UID FLAGS BODY.PEEK[])')
        check(status,'This email could not be read.')
        row=next((row for row in rows if isinstance(row,tuple)),None)
        if row is None: raise RuntimeError('This email is no longer available.')
        payload=message_payload(row[1],row[0],message_id,folder)
        payload['payload'].update(mime_payload(BytesParser(policy=email.policy.default).parsebytes(row[1])))
        return payload


def conversation_messages(config, current, folder):
    references = re.findall(r'<[^<>\s\x00-\x1f\x7f]+@[^<>\s\x00-\x1f\x7f]+>',
        current.get('references','')+' '+current.get('in_reply_to','')+' '+current.get('message_id',''))
    if not references: return []
    root = ('"'+references[0].replace('\\','\\\\').replace('"','\\"')+'"').encode('ascii')
    folders = list(dict.fromkeys(['inbox' if folder=='starred' else folder, 'inbox', 'sent', 'archive']))
    messages = {}
    with imap_connect(config) as client:
        for mail_folder in folders:
            if mail_folder not in config['folders']: continue
            validity = select_folder(client, config, mail_folder)
            status, result = client.uid('SEARCH', None, 'UNDELETED', 'OR', 'OR', 'HEADER', 'Message-ID', root,
                'HEADER', 'References', root, 'HEADER', 'In-Reply-To', root)
            check(status, 'The server could not search the conversation.')
            ids = [str(int(uid)) for uid in (result[0] or b'').split()]
            for start in range(0, len(ids), 100):
                status, rows = client.uid('FETCH', ','.join(ids[start:start+100]),
                    '(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE REPLY-TO TO MESSAGE-ID REFERENCES IN-REPLY-TO)])')
                check(status, 'The server could not read the conversation.')
                for row in rows or []:
                    if not isinstance(row, tuple): continue
                    uid = re.search(rb'UID (\d+)', row[0])
                    if not uid: continue
                    identifier = make_id(config, mail_folder, validity, int(uid[1]))
                    payload = message_payload(row[1], row[0], identifier, mail_folder)
                    payload['mail_folder'] = mail_folder
                    header_id = BytesParser(policy=email.policy.default).parsebytes(row[1]).get('Message-ID')
                    key = str(header_id) if header_id else identifier
                    if key not in messages or identifier==current['id']: messages[key] = payload
    return list(messages.values())


def change_messages(config,ids,action,folder='inbox'):
    with imap_connect(config) as client:
        validity=select_folder(client,config,folder,readonly=False)
        uids=','.join(parse_id(config,item,validity,folder) for item in ids)
        changes={'read':('+FLAGS.SILENT','(\\Seen)'), 'unread':('-FLAGS.SILENT','(\\Seen)'), 'star':('+FLAGS.SILENT','(\\Flagged)'), 'unstar':('-FLAGS.SILENT','(\\Flagged)')}
        if action in changes:
            status,_=client.uid('STORE',uids,*changes[action]);check(status,'The server could not update these messages.');return
        target={'archive':'archive','trash':'trash','restore':'inbox'}[action]
        target_name=mailbox_name(config,target)
        if b'MOVE' in client.capabilities:
            status,_=client.uid('MOVE',uids,target_name);check(status,'The server could not move these messages.')
        else:
            status,_=client.uid('COPY',uids,target_name);check(status,'The server could not copy these messages.')
            status,_=client.uid('STORE',uids,'+FLAGS.SILENT','(\\Deleted)');check(status,'Messages were copied, but the originals could not be hidden.')
            if b'UIDPLUS' in client.capabilities:
                status,_=client.uid('EXPUNGE',uids);check(status,'The server could not finish moving the selected messages.')


def send_message(config,message):
    if not message.get('Date'): message['Date']=formatdate(localtime=True)
    if not message.get('Message-ID'): message['Message-ID']=make_msgid()
    with smtp_connect(config) as client:
        refused=client.send_message(message)
        if refused: raise RuntimeError('The mail server rejected a recipient.')
    if config.get('save_sent',True):
        try:
            with imap_connect(config) as client:
                status,_=client.append(mailbox_name(config,'sent'),'(\\Seen)',None,message.as_bytes(policy=email.policy.SMTP))
                check(status,'Sent copy could not be saved.')
        except (RuntimeError,OSError,imaplib.IMAP4.error):
            # Delivery succeeded; never invite a retry that would send a duplicate.
            return 'Message sent, but its Sent copy could not be saved. Do not send it again.'
    return None
