"""Microsoft Graph mail with account-bound IDs and validated page links."""
import base64
from datetime import datetime
from urllib.parse import urlparse, quote
import requests

BASE='https://graph.microsoft.com/v1.0'
FOLDERS={'inbox':'inbox','sent':'sentitems','drafts':'drafts','trash':'deleteditems','spam':'junkemail','archive':'archive'}


def request(token,method,path,params=None,payload=None):
    response=requests.request(method,BASE+path,headers={'Authorization':'Bearer '+token,'Prefer':'IdType="ImmutableId"'},params=params,json=payload,timeout=(5,20),allow_redirects=False)
    if 300 <= response.status_code < 400: raise RuntimeError('Microsoft returned an unexpected redirect.')
    response.raise_for_status()
    return response.json() if response.content else {}


def encode(value):
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip('=')


def decode(value):
    try: return base64.b64decode(value+'='*(-len(value)%4),altchars=b'-_',validate=True).decode()
    except (ValueError,UnicodeError): raise ValueError('Invalid Microsoft mail identifier.') from None


def message_id(config,raw_id): return 'ms-'+config['account_id']+'-'+encode(raw_id)


def raw_id(config,identifier):
    prefix='ms-'+config['account_id']+'-'
    if not identifier.startswith(prefix): raise ValueError('This email belongs to a different account.')
    return quote(decode(identifier[len(prefix):]),safe='')


def metadata(config,item,folder):
    sender=(item.get('from') or {}).get('emailAddress') or {}
    value=item.get('receivedDateTime','')
    try: timestamp=int(datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()*1000)
    except ValueError: timestamp=0
    labels=[]
    if not item.get('isRead',True): labels.append('UNREAD')
    if (item.get('flag') or {}).get('flagStatus')=='flagged': labels.append('STARRED')
    if folder=='inbox':labels.append('INBOX')
    if folder=='sent':labels.append('SENT')
    if folder=='drafts':labels.append('DRAFT')
    if folder=='trash':labels.append('TRASH')
    if folder=='spam':labels.append('SPAM')
    return {'id':message_id(config,item['id']),'labelIds':labels,'internalDate':str(timestamp),'snippet':item.get('bodyPreview',''),
        'payload':{'headers':[{'name':'From','value':f"{sender.get('name','')} <{sender.get('address','')}>"}, {'name':'Subject','value':item.get('subject','')}, {'name':'Date','value':datetime.fromtimestamp(timestamp/1000).astimezone().strftime('%a, %d %b %Y %H:%M:%S %z') if timestamp else ''}]}}


def list_messages(token,config,folder,query='',cursor=''):
    path='/me/messages' if folder in {'all','starred'} else '/me/mailFolders/'+FOLDERS[folder]+'/messages'
    params={'$top':25,'$select':'id,from,subject,bodyPreview,receivedDateTime,isRead,flag'}
    if query: params['$search']='"'+query.replace('\\','\\\\').replace('"','\\"')+'"'
    else: params['$orderby']='receivedDateTime desc'
    if folder=='starred' and not query:
        # Graph requires ordered properties to appear first in filtered queries.
        params['$filter']="receivedDateTime ge 1900-01-01T00:00:00Z and flag/flagStatus eq 'flagged'"
    if cursor:
        parsed=urlparse(decode(cursor))
        if parsed.scheme!='https' or parsed.netloc!='graph.microsoft.com' or parsed.path != '/v1.0'+path or parsed.fragment:
            raise ValueError('Invalid Microsoft mail page.')
        path+='?'+parsed.query;params=None
    data=request(token,'GET',path,params=params)
    items=data.get('value',[])
    if folder=='starred' and query:items=[item for item in items if (item.get('flag') or {}).get('flagStatus')=='flagged']
    return [metadata(config,item,folder) for item in items],encode(data['@odata.nextLink']) if data.get('@odata.nextLink') else None,data.get('@odata.count')


def read_message(token,config,identifier,folder):
    item=request(token,'GET','/me/messages/'+raw_id(config,identifier))
    data=metadata(config,item,folder)
    body=item.get('body') or {}
    data['payload'].update(mimeType='text/html' if body.get('contentType','').lower()=='html' else 'text/plain',body={'data':base64.urlsafe_b64encode(body.get('content','').encode()).decode()})
    return data


def change_messages(token,config,ids,action):
    paths=['/me/messages/'+raw_id(config,identifier) for identifier in ids]
    for path in paths:
        if action in {'read','unread'}:request(token,'PATCH',path,payload={'isRead':action=='read'})
        elif action in {'star','unstar'}:request(token,'PATCH',path,payload={'flag':{'flagStatus':'flagged' if action=='star' else 'notFlagged'}})
        else:request(token,'POST',path+'/move',payload={'destinationId':{'archive':'archive','trash':'deleteditems','restore':'inbox'}[action]})


def send_message(token,recipient,subject,body):
    request(token,'POST','/me/sendMail',payload={'message':{'subject':subject,'body':{'contentType':'Text','content':body},'toRecipients':[{'emailAddress':{'address':recipient}}]},'saveToSentItems':True})
