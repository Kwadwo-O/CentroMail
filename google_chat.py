"""Google Chat user messaging through CentroMail's existing Google transport."""
import json
import mimetypes
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlparse

from werkzeug.utils import secure_filename
from google_transport import google_requests

SCOPES = ' '.join('https://www.googleapis.com/auth/' + name for name in
    ('chat.spaces', 'chat.messages', 'chat.memberships.readonly'))
BASE = 'https://chat.googleapis.com/v1/'
FILE_LIMIT = 64 * 1024 * 1024


class ChatError(RuntimeError):
    def __init__(self, message, status=502):
        super().__init__(message); self.status = status


def resource(value, kind='space', space=None):
    patterns = {'space':r'spaces/[A-Za-z0-9_-]{1,128}',
        'message':r'spaces/[A-Za-z0-9_-]{1,128}/messages/[A-Za-z0-9_.-]{1,256}',
        'thread':r'spaces/[A-Za-z0-9_-]{1,128}/threads/[A-Za-z0-9_.-]{1,256}',
        'reaction':r'spaces/[A-Za-z0-9_-]{1,128}/messages/[A-Za-z0-9_.-]{1,256}/reactions/[A-Za-z0-9_.-]{1,256}'}
    if not isinstance(value, str) or not re.fullmatch(patterns[kind], value) or any(part in {'.','..'} for part in value.split('/')) or (space and not value.startswith(space + '/')):
        raise ValueError('Invalid Google Chat conversation or message.')
    return value


def check_response(response):
    if 200 <= response.status_code < 300: return
    try: error = response.json().get('error', {})
    except ValueError: error = {}
    detail = error.get('message', '')
    reasons = {item.get('reason') for item in error.get('details', [])}
    if response.status_code == 401:
        message = 'Reconnect Google Chat to refresh your Google access.'
    elif response.status_code == 403:
        message = 'Enable the Google Chat API in your Google Cloud project and reconnect Google Chat.' if reasons & {'SERVICE_DISABLED','ACCESS_TOKEN_SCOPE_INSUFFICIENT'} or 'not been used' in detail or 'insufficient authentication scopes' in detail.lower() else 'Your Google account does not have permission for this Chat action. Your Workspace administrator may need to enable Chat.'
    elif response.status_code == 404:
        message = 'This Google Chat conversation or message is no longer available.'
    elif response.status_code == 429:
        message = 'Google Chat is busy. Wait a moment before trying again.'
    else:
        message = detail or 'Google Chat could not confirm the request. Keep your draft and refresh before retrying.'
    raise ChatError(message, response.status_code if response.status_code >= 400 else 502)


def request(token, method, path, *, params=None, payload=None):
    response = google_requests.request(method, BASE + quote(path, safe='/:'),
        headers={'Authorization':'Bearer ' + token}, params=params, json=payload, allow_redirects=False)
    check_response(response)
    return response.json() if response.content else {}


def own_message(item, me):
    sender = item.get('sender') or {}
    return bool((me.get('id') and sender.get('name') == 'users/' + me['id']) or
                (sender.get('email') and sender['email'].lower() == me['email'].lower()))


def message_data(item, me):
    sender = item.get('sender') or {}
    deleted = bool(item.get('deleteTime'))
    own = own_message(item, me) and not deleted
    attachments = []
    for index, attachment in enumerate(item.get('attachment') or []):
        url = attachment.get('downloadUri', '')
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.hostname or not (parsed.hostname.endswith('.google.com') or parsed.hostname.endswith('.googleusercontent.com')): url = ''
        attachments.append({'index':index, 'name':attachment.get('contentName') or 'Attachment',
            'downloadable':bool((attachment.get('attachmentDataRef') or {}).get('resourceName')), 'url':url})
    return {'id':resource(item['name'],'message'), 'sender':'You' if own else sender.get('displayName') or sender.get('email') or 'Google Chat',
        'outgoing':own, 'text':'Message deleted.' if deleted else item.get('text') or item.get('fallbackText') or '',
        'time':item.get('createTime', ''), 'updated':item.get('lastUpdateTime', ''), 'deleted':deleted,
        'thread':(item.get('thread') or {}).get('name'), 'thread_reply':bool(item.get('threadReply')),
        'can_edit':own, 'can_delete':own, 'attachments':attachments,
        'reactions':[{'emoji':(item.get('emoji') or {}).get('unicode',''), 'count':item.get('reactionCount',0)} for item in item.get('emojiReactionSummaries',[]) if (item.get('emoji') or {}).get('unicode')]}


def space_data(item):
    name = resource(item['name'])
    return {'id':name, 'name':item.get('displayName') or ('Direct message' if item.get('spaceType') == 'DIRECT_MESSAGE' else 'Group chat'),
        'kind':item.get('spaceType','SPACE'), 'url':'https://chat.google.com/room/' + name.split('/')[1]}


def spaces(token, me, cursor=None):
    if cursor and (len(cursor) > 4096 or any(ord(char) < 32 for char in cursor)): raise ValueError('Invalid Google Chat page.')
    data = request(token, 'GET', 'spaces', params={'pageSize':50, **({'pageToken':cursor} if cursor else {})})
    def describe(item):
        result = space_data(item)
        if not item.get('displayName'):
            members = request(token, 'GET', result['id'] + '/members', params={'pageSize':100}).get('memberships', [])
            names = [member.get('displayName') or member.get('email') for entry in members if
                (member := entry.get('member') or {}).get('type') == 'HUMAN' and not own_message({'sender':member}, me)]
            result['name'] = ', '.join(filter(None, names)) or result['name']
        return result
    with ThreadPoolExecutor(max_workers=6) as pool:
        conversations = list(pool.map(describe, data.get('spaces', [])))
    return {'conversations':conversations, 'next_cursor':data.get('nextPageToken')}


def create_space(token, kind, title, members, request_id):
    if kind not in {'DIRECT_MESSAGE','GROUP_CHAT','SPACE'} or (kind == 'DIRECT_MESSAGE' and len(members) != 1) or (kind == 'GROUP_CHAT' and len(members) < 2) or len(members) > 49:
        raise ValueError('Choose one person for a direct message, or at least two for a group chat.')
    if kind == 'SPACE' and (not title.strip() or len(title) > 128): raise ValueError('Give the space a name of up to 128 characters.')
    payload = {'space':{'spaceType':kind}, 'requestId':request_id,
        'memberships':[{'member':{'name':'users/' + email, 'type':'HUMAN'}} for email in members]}
    if kind == 'SPACE': payload['space']['displayName'] = title.strip()
    if kind == 'DIRECT_MESSAGE': payload['space']['singleUserBotDm'] = False
    return space_data(request(token, 'POST', 'spaces:setup', payload=payload))


def messages(token, me, space, cursor=None, known_ids=(), after=None):
    resource(space)
    if cursor and (len(cursor) > 4096 or any(ord(char) < 32 for char in cursor)): raise ValueError('Invalid Google Chat page.')
    for name in known_ids: resource(name, 'message', space)
    if after and not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})',after): raise ValueError('Invalid Google Chat message time.')
    data = request(token, 'GET', space + '/messages', params={'pageSize':50, 'orderBy':'create_time ASC' if after else 'create_time DESC', 'showDeleted':True,
        **({'pageToken':cursor} if cursor else {}), **({'filter':f'create_time > "{after}"'} if after else {})})
    raw = data.get('messages', [])
    items = [message_data(item, me) for item in (raw if after else reversed(raw))]
    seen = {item['id'] for item in items}
    def update(name):
        try: return message_data(request(token, 'GET', name), me)
        except ChatError as error:
            if error.status != 404: raise
            return {'id':name, 'deleted':True}
    with ThreadPoolExecutor(max_workers=6) as pool:
        updates = list(pool.map(update, [name for name in known_ids if name not in seen]))
    return {'messages':items, 'updated_messages':updates, 'next_cursor':data.get('nextPageToken')}


def send(token, space, text, request_id, reply=None, attachment=None):
    resource(space)
    payload = {'text':text}
    params = {'requestId':request_id}
    if attachment: payload['attachment'] = [{'attachmentDataRef':attachment}]
    if not text.strip() and not attachment: raise ValueError('Write a message or attach a file.')
    if reply:
        resource(reply, 'message', space)
        original = request(token, 'GET', reply)
        room = request(token, 'GET', space)
        payload['quotedMessageMetadata'] = {'name':reply, 'lastUpdateTime':original.get('lastUpdateTime') or original['createTime']}
        if room.get('spaceType') == 'SPACE':
            payload['thread'] = {'name':resource(original['thread']['name'],'thread',space)}
            params['messageReplyOption'] = 'REPLY_MESSAGE_OR_FAIL'
    if len(json.dumps(payload,ensure_ascii=False).encode()) > 32000: raise ValueError('The message exceeds Google Chat’s 32,000-byte limit.')
    sent = request(token, 'POST', space + '/messages', params=params, payload=payload)
    if not sent.get('sender') or not sent.get('createTime'):
        sent = request(token, 'GET', resource(sent['name'], 'message', space))
    return sent


def change_message(token, me, name, action, *, text='', original=None, force=False, emoji=''):
    resource(name,'message')
    item = request(token, 'GET', name)
    if action in {'edit','delete'} and not own_message(item,me): raise ValueError('You can only edit or delete your own Google Chat messages.')
    if action == 'edit':
        if not text.strip() or len(json.dumps({'text':text},ensure_ascii=False).encode()) > 32000: raise ValueError('Write a message within Google Chat’s 32,000-byte limit.')
        if original is not None and item.get('text','') != original and item.get('text','') != text: raise ValueError('This message changed. Cancel and refresh before editing again.')
        item = request(token, 'PATCH', name, params={'updateMask':'text'}, payload={'text':text})
    elif action == 'delete':
        request(token, 'DELETE', name, params={'force':str(force).lower()})
        return {'deleted':True,'id':name}
    elif action == 'reaction':
        if not emoji or len(emoji.encode('utf-16-le')) // 2 > 32 or any(ord(char) < 32 for char in emoji): raise ValueError('Choose an emoji reaction.')
        filter_name = 'users/' + me['id'] if me.get('id') else 'users/' + me['email']
        data = request(token, 'GET', name + '/reactions', params={'pageSize':100,'filter':'user.name = "' + filter_name + '"'})
        previous = next((item for item in data.get('reactions',[]) if (item.get('emoji') or {}).get('unicode') == emoji), None)
        if previous: request(token, 'DELETE', resource(previous['name'],'reaction',name))
        else: request(token, 'POST', name + '/reactions', payload={'emoji':{'unicode':emoji}})
        item = request(token, 'GET', name)
    else: raise ValueError('Invalid Google Chat message action.')
    return {'message':message_data(item,me)}


def upload(token, space, filename, content):
    resource(space)
    if not content or len(content) > FILE_LIMIT: raise ValueError('Choose a file of up to 64 MB.')
    filename = secure_filename(filename) or 'attachment.bin'
    boundary = 'centromail-' + secrets.token_hex(16)
    mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    data = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode() +
        json.dumps({'filename':filename}).encode() + f'\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n'.encode() + content + f'\r\n--{boundary}--\r\n'.encode())
    response = google_requests.request('POST', 'https://chat.googleapis.com/upload/v1/' + quote(space,safe='/') + '/attachments:upload',
        headers={'Authorization':'Bearer ' + token,'Content-Type':'multipart/related; boundary=' + boundary},
        params={'uploadType':'multipart'}, data=data, timeout=(5,60), allow_redirects=False)
    check_response(response)
    return response.json()['attachmentDataRef']


def download(token, name):
    if not isinstance(name,str) or len(name) > 4096 or any(part in {'.','..'} for part in name.split('/')) or not name.startswith('spaces/'):
        raise ValueError('Invalid Google Chat attachment.')
    response = google_requests.request('GET', BASE + 'media/' + quote(name,safe='/'),
        headers={'Authorization':'Bearer ' + token}, params={'alt':'media'}, stream=True, allow_redirects=False, timeout=(5,60))
    try:
        check_response(response)
        if response.status_code != 200: raise ValueError('The attachment could not be downloaded.')
        if int(response.headers.get('Content-Length','0')) > FILE_LIMIT: raise ValueError('Open Google Chat to download files larger than 64 MB.')
        chunks = []; length = 0
        for chunk in response.iter_content(512 * 1024):
            length += len(chunk)
            if length > FILE_LIMIT: raise ValueError('Open Google Chat to download files larger than 64 MB.')
            chunks.append(chunk)
        return b''.join(chunks)
    finally: response.close()
