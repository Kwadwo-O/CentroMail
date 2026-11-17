"""Google Chat integration using disposable users and mocked provider responses."""
import io
import json
from unittest.mock import Mock, patch

import requests
import app as a
import google_chat as chat
from test_integrations import IntegrationFixture


def response(data=None, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(data or {}).encode()
    return result


class GoogleChatTests(IntegrationFixture):
    def setUp(self):
        super().setUp()
        self.login()
        self.token = {'access_token':'chat-token', 'refresh_token':'refresh-only-test',
            'expires_at':a.time.time()+3600, 'scope':chat.SCOPES,
            'userinfo':{'sub':'123','email':'integrations@example.com','email_verified':True}}
        with a.app.app_context():
            a.store_google_token(self.user_id, self.token)
            a.save_integration(self.user_id, 'google_chat', {'account_key':'gmail'})
        self.http = patch('google_transport.GoogleRequests.request')
        self.provider = self.http.start()
        self.addCleanup(self.http.stop)
        self.provider.return_value = response()

    def message(self, identifier='first', text='Hello', own=True, **extra):
        return {'name':'spaces/room/messages/'+identifier, 'text':text,
            'sender':{'name':'users/123' if own else 'users/456','displayName':'Friend'},
            'createTime':'2026-11-17T12:00:00Z', 'thread':{'name':'spaces/room/threads/thread'}, **extra}

    def post(self, path, **data):
        return self.client.post(path, data={'csrf_token':'test-token', **data})

    def test_cards_and_workspace_use_owned_gmail_account_and_disconnect_keeps_mail(self):
        body = self.client.get('/integrations').data
        self.assertIn(b'Google Chat', body)
        self.assertIn(b'Reconnect Google Chat', body)
        with a.app.test_request_context():
            connections = a.workspace_connections(a.find_user('integrations@example.com'))
        self.assertIn('google-chat', [item['key'] for item in connections])
        page = self.client.get('/inbox').text
        self.assertIn('data-app-provider="google-chat"', page)
        self.assertIn('data-app-feed="/api/integrations/google-chat/spaces" data-app-connected="true"', page)
        self.assertEqual(self.post('/integrations/google-chat/disconnect').status_code, 302)
        with a.app.app_context():
            self.assertIsNone(a.get_integration(self.user_id, 'google_chat'))
            self.assertEqual(a.get_google_token(a.find_user('integrations@example.com'))['access_token'], 'chat-token')
        self.provider.assert_not_called()

    def test_google_chat_is_visible_in_apps_before_connecting_without_provider_requests(self):
        with a.app.app_context():
            a.delete_integration(self.user_id, 'google_chat')
            a.store_google_token(self.user_id, None)
        page = self.client.get('/inbox').text
        self.assertIn('data-app-provider="google-chat"', page)
        self.assertIn('data-app-feed="" data-app-connected="false"', page)
        self.assertIn('id="apps-connection-prompt"', page)
        self.assertIn('href="/integrations/google-chat/connect"', page)
        self.assertIn('id="google-chat-workspace"', page)
        self.provider.assert_not_called()

    def test_apps_offer_reconnection_when_chat_permissions_or_account_are_missing(self):
        with a.app.app_context(): a.store_google_token(self.user_id, {**self.token,'scope':'gmail.readonly'})
        self.assertIn('data-app-feed="" data-app-connected="false"', self.client.get('/inbox').text)
        with a.app.app_context(): a.save_integration(self.user_id, 'google_chat', {'account_key':'email:gmail:foreign'})
        self.assertIn('data-app-feed="" data-app-connected="false"', self.client.get('/inbox').text)
        self.provider.assert_not_called()

    def test_token_refresh_uses_gmail_credentials_and_preserves_scopes(self):
        with a.app.app_context():
            a.store_google_token(self.user_id, {**self.token,'expires_at':0})
        def transport(method, url, **kwargs):
            if url == 'https://oauth2.googleapis.com/token':
                self.assertEqual(kwargs['data']['refresh_token'], 'refresh-only-test')
                return response({'access_token':'fresh-chat','expires_in':3600})
            self.assertEqual(kwargs['headers']['Authorization'], 'Bearer fresh-chat')
            return response({'spaces':[]})
        self.provider.side_effect = transport
        self.assertEqual(self.client.get('/api/integrations/google-chat/spaces').status_code, 200)
        with a.app.app_context():
            stored = a.get_google_token(a.find_user('integrations@example.com'))
        self.assertEqual((stored['access_token'], stored['scope']), ('fresh-chat', chat.SCOPES))
        self.assertEqual(self.provider.call_count, 2)

    def test_secondary_account_uses_its_token_and_missing_or_foreign_accounts_are_rejected(self):
        with a.app.app_context():
            a.save_integration(self.user_id, 'email:gmail:second', {'kind':'gmail','name':'Gmail','email':'second@example.com',
                'account_id':'a'*12,'token':{**self.token,'access_token':'second-token'}})
            a.save_integration(self.user_id, 'google_chat', {'account_key':'email:gmail:second'})
        self.provider.return_value = response({'spaces':[]})
        self.assertEqual(self.client.get('/api/integrations/google-chat/spaces').status_code, 200)
        self.assertEqual(self.provider.call_args.kwargs['headers']['Authorization'], 'Bearer second-token')
        with a.app.app_context():
            a.save_integration(self.user_id, 'google_chat', {'account_key':'email:gmail:foreign'})
        self.provider.reset_mock()
        self.assertEqual(self.client.get('/api/integrations/google-chat/spaces').status_code, 409)
        self.provider.assert_not_called()

    def test_auth_scopes_csrf_and_input_checks_prevent_provider_calls(self):
        path = '/api/integrations/google-chat/spaces/room/messages'
        self.assertEqual(a.app.test_client().get(path).status_code, 302)
        self.assertEqual(self.client.post(path, data={'text':'Hi'}).status_code, 400)
        self.assertEqual(self.post(path, text='Hi', request_id='bad').status_code, 400)
        self.assertEqual(self.client.get(path+'?known_ids=../other').status_code, 400)
        self.assertEqual(self.client.get(path+'?known_ids='+','.join(['first']*51)).status_code, 400)
        with a.app.app_context(): a.store_google_token(self.user_id, {**self.token,'scope':'gmail.readonly'})
        self.assertEqual(self.client.get(path).status_code, 409)
        self.provider.assert_not_called()

    def test_google_oauth_requests_chat_scopes_and_callback_links_same_account(self):
        original = {key:a.app.config[key] for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REDIRECT_URI')}
        self.addCleanup(a.app.config.update, original)
        a.app.config.update(GOOGLE_CLIENT_ID='test-id',GOOGLE_CLIENT_SECRET='test-secret',GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback')
        with patch.object(a.google, 'authorize_redirect', return_value=a.redirect('/consent')) as authorize:
            self.assertEqual(self.client.get('/auth/google?connect=1&service=chat').status_code, 302)
        options = authorize.call_args.kwargs
        self.assertTrue(set(chat.SCOPES.split()).issubset(set(options['scope'].split())))
        self.assertIn('https://www.googleapis.com/auth/gmail.modify', options['scope'])
        self.assertEqual(options['include_granted_scopes'], 'true')
        with patch.object(a.google, 'authorize_access_token', return_value=self.token):
            result = self.client.get('/auth/google/callback')
        self.assertTrue(result.location.endswith('/inbox#apps'))
        with a.app.app_context(): self.assertEqual(a.get_integration(self.user_id,'google_chat')['account_key'],'gmail')
        self.provider.assert_not_called()

    def test_loopback_redirect_preserves_chat_intent(self):
        original = {key:a.app.config[key] for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REDIRECT_URI')}
        self.addCleanup(a.app.config.update, original)
        a.app.config.update(GOOGLE_CLIENT_ID='test-id',GOOGLE_CLIENT_SECRET='test-secret',GOOGLE_REDIRECT_URI='http://localhost:5000/auth/google/callback')
        with self.client.session_transaction(base_url='http://127.0.0.1:5000') as session:
            session['user_id'] = self.user_id
            session['user_email'] = 'integrations@example.com'
        with patch.object(a.google,'authorize_redirect') as authorize:
            result = self.client.get('/auth/google?connect=1&service=chat',base_url='http://127.0.0.1:5000')
        self.assertIn('connect=1&service=chat', result.location)
        authorize.assert_not_called()

    def test_space_names_exclude_self_and_new_chats_validate_participants(self):
        def transport(method,url,**kwargs):
            if url.endswith('/spaces'): return response({'spaces':[{'name':'spaces/room','spaceType':'DIRECT_MESSAGE'}]})
            return response({'memberships':[{'member':{'name':'users/123','type':'HUMAN','displayName':'Me'}},
                {'member':{'name':'users/456','type':'HUMAN','displayName':'Friend'}}]})
        self.provider.side_effect = transport
        self.assertEqual(self.client.get('/api/integrations/google-chat/spaces').json['conversations'][0]['name'],'Friend')
        self.provider.side_effect = None
        self.provider.return_value = response({'name':'spaces/room','spaceType':'DIRECT_MESSAGE'})
        self.assertEqual(self.post('/api/integrations/google-chat/spaces',kind='DIRECT_MESSAGE',members='friend@example.com',request_id='a'*32).status_code,200)
        payload = self.provider.call_args.kwargs['json']
        self.assertEqual(payload['memberships'][0]['member']['name'],'users/friend@example.com')
        self.provider.reset_mock()
        self.assertEqual(self.post('/api/integrations/google-chat/spaces',members='integrations@example.com',request_id='a'*32).status_code,400)
        self.provider.assert_not_called()

    def test_history_deltas_update_deleted_messages_and_cursor_is_bound_to_account_space(self):
        path = '/api/integrations/google-chat/spaces/room/messages'
        def transport(method,url,**kwargs):
            if url.endswith('/messages'): return response({'messages':[self.message('second'),self.message('first')], 'nextPageToken':'provider-page'})
            return response({'error':{'message':'gone'}},404)
        self.provider.side_effect = transport
        data = self.client.get(path+'?known_ids=gone').json
        self.assertEqual([item['id'].split('/')[-1] for item in data['messages']], ['first','second'])
        self.assertTrue(data['updated_messages'][0]['deleted'])
        cursor = data['next_cursor']
        self.assertNotEqual(cursor,'provider-page')
        self.provider.reset_mock()
        self.assertEqual(self.client.get(path.replace('/room/','/other/'),query_string={'cursor':cursor}).status_code,400)
        self.provider.assert_not_called()
        self.assertEqual(self.client.get(path,query_string={'after':'2026-11-17T12:00:00Z'}).status_code,200)
        params = next(call.kwargs['params'] for call in self.provider.call_args_list if call.args[1].endswith('/messages'))
        self.assertEqual(params['orderBy'],'create_time ASC')
        self.assertIn('create_time >',params['filter'])

    def test_sends_are_idempotent_and_replies_preserve_quote_revision_and_thread(self):
        path = '/api/integrations/google-chat/spaces/room/messages'
        def transport(method,url,**kwargs):
            if method == 'POST': return response({'name':'spaces/room/messages/sent'})
            if url.endswith('/room'): return response({'spaceType':'SPACE'})
            return response(self.message('sent' if url.endswith('/sent') else 'first',lastUpdateTime='2026-11-17T12:01:00Z'))
        self.provider.side_effect = transport
        for _ in range(2):
            data = self.post(path,text='A reply',request_id='b'*32,reply='spaces/room/messages/first')
            self.assertEqual(data.status_code,200)
            self.assertTrue(data.json['message']['outgoing'])
        sends = [call for call in self.provider.call_args_list if call.args[0] == 'POST']
        self.assertEqual([call.kwargs['params']['requestId'] for call in sends],['b'*32]*2)
        self.assertEqual(sends[0].kwargs['json']['quotedMessageMetadata']['lastUpdateTime'],'2026-11-17T12:01:00Z')
        self.assertEqual(sends[0].kwargs['params']['messageReplyOption'],'REPLY_MESSAGE_OR_FAIL')
        self.assertEqual(sends[0].kwargs['json']['thread']['name'],'spaces/room/threads/thread')

    def test_edit_delete_ownership_conflicts_and_explicit_thread_deletion(self):
        path = '/api/integrations/google-chat/spaces/room/messages/first/actions'
        self.provider.return_value = response(self.message(own=False))
        for action in ('edit','delete'):
            self.assertEqual(self.post(path,action=action,text='Changed').status_code,400)
        self.assertTrue(all(call.args[0] == 'GET' for call in self.provider.call_args_list))
        self.provider.return_value = response(self.message())
        self.assertEqual(self.post(path,action='edit',text='Changed',original='Stale').status_code,400)
        self.provider.side_effect = [response(self.message()),response(self.message(text='Changed'))]
        self.assertEqual(self.post(path,action='edit',text='Changed',original='Hello').status_code,200)
        self.assertEqual(self.provider.call_args.kwargs['params'],{'updateMask':'text'})
        self.provider.side_effect = [response(self.message()),response()]
        self.assertTrue(self.post(path,action='delete',force='true').json['deleted'])
        self.assertEqual(self.provider.call_args.kwargs['params'],{'force':'true'})

    def test_reactions_toggle_only_authenticated_users_reaction(self):
        path = '/api/integrations/google-chat/spaces/room/messages/first/actions'
        self.provider.side_effect = [response(self.message()),response({'reactions':[]}),response(),response(self.message())]
        self.assertEqual(self.post(path,action='reaction',emoji='👍').status_code,200)
        calls = self.provider.call_args_list
        self.assertIn('users/123',calls[1].kwargs['params']['filter'])
        self.assertEqual(calls[2].kwargs['json'],{'emoji':{'unicode':'👍'}})
        reaction = {'name':'spaces/room/messages/first/reactions/reaction','emoji':{'unicode':'👍'}}
        self.provider.reset_mock()
        self.provider.side_effect = [response(self.message()),response({'reactions':[reaction]}),response(),response(self.message())]
        self.assertEqual(self.post(path,action='reaction',emoji='👍').status_code,200)
        self.assertEqual(self.provider.call_args_list[2].args[0],'DELETE')

    def test_upload_token_is_bound_to_space_and_downloads_are_bounded_safe_attachments(self):
        self.provider.return_value = response({'attachmentDataRef':{'attachmentUploadToken':'provider-ref'}})
        result = self.post('/api/integrations/google-chat/spaces/room/attachments',file=(io.BytesIO(b'test-file'),'example.html'))
        self.assertEqual(result.status_code,200)
        call = self.provider.call_args
        self.assertIn('/upload/v1/spaces/room/attachments:upload',call.args[1])
        self.assertIn(b'"filename": "example.html"',call.kwargs['data'])
        signed = result.json['attachment_token']
        self.provider.reset_mock()
        self.assertEqual(self.post('/api/integrations/google-chat/spaces/other/messages',text='',request_id='c'*32,attachment_token=signed).status_code,400)
        self.provider.assert_not_called()
        attachment = {'contentName':'example.html','attachmentDataRef':{'resourceName':'spaces/room/attachments/file'}}
        stream = Mock(status_code=200,headers={'Content-Length':'7'})
        stream.iter_content.return_value = [b'<html/>']
        self.provider.side_effect = [response(self.message(attachment=[attachment])),stream]
        result = self.client.get('/api/integrations/google-chat/spaces/room/messages/first/attachments/0')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.mimetype,'application/octet-stream')
        self.assertIn('attachment;',result.headers['Content-Disposition'])
        self.assertEqual(result.headers['X-Content-Type-Options'],'nosniff')
        stream.close.assert_called_once()
        self.provider.side_effect = None
        stream.headers = {}; stream.iter_content.return_value = [b'12345',b'67890']; self.provider.return_value = stream
        with patch.object(chat,'FILE_LIMIT',8), self.assertRaises(ValueError): chat.download('token','spaces/room/attachments/file')

    def test_provider_setup_error_is_actionable_and_redirects_are_rejected(self):
        self.provider.return_value = response({'error':{'details':[{'reason':'SERVICE_DISABLED'}]}},403)
        result = self.client.get('/api/integrations/google-chat/spaces')
        self.assertEqual(result.status_code,403)
        self.assertIn('Enable the Google Chat API',result.json['error'])
        self.provider.return_value = response(status=302)
        self.assertEqual(self.client.get('/api/integrations/google-chat/spaces').status_code,502)
        self.assertFalse(self.provider.call_args.kwargs['allow_redirects'])

    def test_signed_pages_and_uploads_cannot_cross_users_or_google_accounts(self):
        from itsdangerous import URLSafeSerializer
        path = '/api/integrations/google-chat/spaces/room/messages'
        for changed in ({'owner':self.user_id+1},{'account':'email:gmail:another'}):
            page = URLSafeSerializer(a.app.config['SECRET_KEY'],salt='google-chat-page').dumps(
                {'owner':self.user_id,'account':'gmail','space':'spaces/room','after':None,'cursor':'next',**changed})
            self.assertEqual(self.client.get(path,query_string={'cursor':page}).status_code,400)
            upload = URLSafeSerializer(a.app.config['SECRET_KEY'],salt='google-chat-attachment').dumps(
                {'owner':self.user_id,'account':'gmail','space':'spaces/room','ref':{'attachmentUploadToken':'ref'},'time':a.time.time(),**changed})
            self.assertEqual(self.post(path,text='Hi',request_id='d'*32,attachment_token=upload).status_code,400)
        self.provider.assert_not_called()

    def test_valid_uploaded_file_reference_reaches_send_and_oversized_uploads_are_rejected(self):
        from itsdangerous import URLSafeSerializer
        path = '/api/integrations/google-chat/spaces/room/messages'
        upload = URLSafeSerializer(a.app.config['SECRET_KEY'],salt='google-chat-attachment').dumps(
            {'owner':self.user_id,'account':'gmail','space':'spaces/room','ref':{'attachmentUploadToken':'ref'},'time':a.time.time()})
        self.provider.return_value = response(self.message())
        self.assertEqual(self.post(path,text='',request_id='e'*32,attachment_token=upload).status_code,200)
        self.assertEqual(self.provider.call_args.kwargs['json']['attachment'],[{'attachmentDataRef':{'attachmentUploadToken':'ref'}}])
        self.provider.reset_mock()
        with patch.object(chat,'FILE_LIMIT',8):
            result = self.post('/api/integrations/google-chat/spaces/room/attachments',file=(io.BytesIO(b'a'*70000),'big.txt'))
        self.assertEqual(result.status_code,413)
        self.provider.assert_not_called()
