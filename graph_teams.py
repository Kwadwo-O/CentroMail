"""Delegated Microsoft Teams chats and channels, with account-bound page cursors."""
from urllib.parse import quote, unquote, urlparse

from itsdangerous import BadSignature
import graph_mail

SCOPES = 'offline_access ' + ' '.join('https://graph.microsoft.com/' + name for name in (
    'User.Read', 'Chat.Read', 'ChatMessage.Send', 'Team.ReadBasic.All',
    'Channel.ReadBasic.All', 'ChannelMessage.Read.All', 'ChannelMessage.Send'))


def segment(value):
    if not isinstance(value, str) or not value or len(value) > 1024 or value in {'.', '..'} or any(ord(char) < 32 or char in '/\\?#' for char in value):
        raise ValueError('Invalid Teams identifier.')
    return quote(value, safe='')


def key(signer, owner, account, kind, identifier, team=None):
    segment(identifier)
    if team is not None: segment(team)
    return signer.dumps({'owner': owner, 'account': account, 'kind': kind, 'id': identifier, 'team': team})


def unpack(signer, owner, account, value, kinds):
    try:
        data = signer.loads(value)
        if data['owner'] != owner or data['account'] != account or data['kind'] not in kinds:
            raise ValueError
        segment(data['id'])
        if data.get('team') is not None: segment(data['team'])
        if data['kind'] == 'channel' and not data.get('team'): raise ValueError
        return data
    except (BadSignature, KeyError, TypeError, ValueError):
        raise ValueError('This Teams conversation is invalid or belongs to another account. Refresh the list.') from None


def next_path(url, target):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'graph.microsoft.com' or unquote(parsed.path) != '/v1.0' + unquote(target) or parsed.fragment:
        raise ValueError('Invalid Teams page.')
    return target + ('?' + parsed.query if parsed.query else '')


def page(token, path, params, cursor, signer, owner, account):
    request_path = path
    if cursor:
        try:
            saved = signer.loads(cursor)
            if saved['owner'] != owner or saved['account'] != account or saved['target'] != path: raise ValueError
            request_path = next_path(saved['url'], path)
        except (BadSignature, KeyError, TypeError, ValueError):
            raise ValueError('Invalid Teams page. Refresh this conversation.') from None
        params = None
    data = graph_mail.request(token, 'GET', request_path, params=params)
    next_url = data.get('@odata.nextLink')
    next_cursor = None
    if next_url:
        next_path(next_url, path)
        next_cursor = signer.dumps({'owner': owner, 'account': account, 'target': path, 'url': next_url})
    return data.get('value', []), next_cursor


def conversations(token, signer, owner, account, kind='chats', team=None, cursor=None):
    team_id = None
    if kind == 'chats':
        path, params = '/me/chats', {'$top': 50, '$expand': 'members', '$orderby': 'lastUpdatedDateTime desc'}
    elif kind == 'teams':
        path, params = '/me/joinedTeams', None
    elif kind == 'channels':
        team_id = unpack(signer, owner, account, team, {'team'})['id']
        path, params = '/teams/' + segment(team_id) + '/channels', None
    else:
        raise ValueError('Choose chats or a team channel.')
    items, next_cursor = page(token, path, params, cursor, signer, owner, account)
    result = []
    for item in items:
        room_kind = {'chats': 'chat', 'teams': 'team', 'channels': 'channel'}[kind]
        names = [member.get('displayName', '') for member in item.get('members', []) if member.get('userId') != account]
        name = item.get('displayName') or item.get('topic') or ', '.join(filter(None, names)) or 'Teams chat'
        result.append({'key': key(signer, owner, account, room_kind, item['id'], team_id),
            'name': name, 'kind': room_kind, 'detail': item.get('membershipType') or item.get('chatType') or 'Team'})
    return {'conversations': result, 'next_cursor': next_cursor}


def messages_path(room):
    if room['kind'] == 'chat': return '/chats/' + segment(room['id']) + '/messages'
    return '/teams/' + segment(room['team']) + '/channels/' + segment(room['id']) + '/messages'


def messages(token, signer, owner, account, conversation, cursor=None, reply=None):
    room = unpack(signer, owner, account, conversation, {'chat', 'channel'})
    path = messages_path(room)
    if reply:
        if room['kind'] != 'channel': raise ValueError('Chat messages do not have channel threads.')
        path += '/' + segment(reply) + '/replies'
    items, next_cursor = page(token, path, {'$top': 50}, cursor, signer, owner, account)
    result = []
    for item in items:
        sender = (item.get('from') or {}).get('user') or (item.get('from') or {}).get('application') or {}
        body = item.get('body') or {}
        url = item.get('webUrl', '')
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'teams.microsoft.com', 'teams.cloud.microsoft'}: url = ''
        result.append({'id': item['id'], 'sender': sender.get('displayName') or 'Teams',
            'text': 'Message deleted.' if item.get('deletedDateTime') else body.get('content', ''),
            'html': body.get('contentType', '').lower() == 'html' and not item.get('deletedDateTime'),
            'time': item.get('createdDateTime', ''), 'outgoing': sender.get('id') == account,
            'url': url, 'subject': item.get('subject') or '',
            'attachments': [attachment.get('name') or 'Attachment' for attachment in item.get('attachments', [])]})
    return {'messages': result, 'next_cursor': next_cursor, 'kind': room['kind']}


def send(token, signer, owner, account, conversation, text, reply=None):
    room = unpack(signer, owner, account, conversation, {'chat', 'channel'})
    path = messages_path(room)
    if reply:
        if room['kind'] != 'channel': raise ValueError('Choose a channel thread to reply.')
        path += '/' + segment(reply) + '/replies'
    return graph_mail.request(token, 'POST', path, payload={'body': {'contentType': 'text', 'content': text}})
