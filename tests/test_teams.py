"""Teams OAuth, account isolation, pagination, and Graph requests without live sends."""
import unittest
from unittest.mock import Mock, patch
from itsdangerous import URLSafeSerializer
import requests
import app as application
import graph_teams
from test_integrations import IntegrationFixture


class TeamsTests(IntegrationFixture):
    def setUp(self):
        super().setUp(); self.login()
        self.signer = URLSafeSerializer(application.app.config['SECRET_KEY'], salt='teams-conversations')
        self.account = 'microsoft-user'
        self.config = {'stage':'connected','account':{'id':self.account,'name':'Example','email':'work@example.com'},
            'token':{'access_token':'private-token','refresh_token':'private-refresh','expires_at':application.time.time()+3600}}
        with application.app.app_context(): application.save_integration(self.user_id, 'teams', self.config)
        self.chat = graph_teams.key(self.signer, self.user_id, self.account, 'chat', '19:chat@thread.v2')
        self.channel = graph_teams.key(self.signer, self.user_id, self.account, 'channel', '19:channel@thread.tacv2', 'team-id')

    def path(self, conversation=None):
        return '/api/integrations/teams/conversations/' + (conversation or self.chat) + '/messages'

    def test_connection_check_uses_saved_teams_token_without_sending(self):
        with patch.object(application.graph_mail, 'request', return_value={'value':[]}) as graph:
            result = self.client.post('/api/integrations/teams/check', data={'csrf_token':'test-token'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(graph.call_args.args, ('private-token', 'GET', '/me/chats'))
        self.assertEqual(graph.call_args.kwargs['params'], {'$top':1})

    def test_pages_render_locally_without_exposing_tokens(self):
        with patch.object(application.graph_mail, 'request', side_effect=AssertionError('Rendering must stay local')):
            page = self.client.get('/integrations')
            self.assertIn(b'Microsoft Teams', page.data)
            self.assertNotIn(b'private-token', page.data); self.assertNotIn(b'private-refresh', page.data)
            self.assertIn(b'data-app-provider="teams"', self.client.get('/inbox').data)

    def test_chats_teams_and_channels_use_their_graph_endpoints(self):
        responses = [{'value':[{'id':'chat','members':[{'userId':self.account,'displayName':'Me'},{'userId':'other','displayName':'Alex'}]}]},
            {'value':[{'id':'team-id','displayName':'Engineering'}]}, {'value':[{'id':'channel','displayName':'General'}]}]
        with patch.object(application.graph_mail, 'request', side_effect=responses) as graph:
            chats = self.client.get('/api/integrations/teams/conversations').json
            teams = self.client.get('/api/integrations/teams/conversations?kind=teams').json
            channels = self.client.get('/api/integrations/teams/conversations', query_string={'kind':'channels','team':teams['conversations'][0]['key']}).json
        self.assertEqual(chats['conversations'][0]['name'], 'Alex'); self.assertEqual(channels['conversations'][0]['name'], 'General')
        self.assertEqual([call.args[2] for call in graph.call_args_list], ['/me/chats','/me/joinedTeams','/teams/team-id/channels'])

    def test_message_html_is_text_and_attachment_urls_stay_private(self):
        item = {'id':'1','from':{'user':{'id':self.account,'displayName':'Example'}},
            'body':{'contentType':'html','content':'<p>Hello <b>Alex</b></p><script>evil()</script>'},
            'webUrl':'javascript:alert(1)','attachments':[{'name':'Notes.pdf','contentUrl':'https://private.example/file'}]}
        with patch.object(application.graph_mail, 'request', return_value={'value':[item]}): response = self.client.get(self.path())
        self.assertEqual(response.status_code, 200)
        message = response.json['messages'][0]
        self.assertTrue(message['outgoing']); self.assertIn('Hello Alex', ' '.join(message['text'].split()))
        self.assertNotIn('evil()', message['text']); self.assertEqual(message['url'], '')
        self.assertNotIn('private.example', response.text)

    def test_foreign_accounts_and_forged_conversations_never_contact_graph(self):
        keys = [graph_teams.key(self.signer,self.user_id+1,self.account,'chat','chat'),
            graph_teams.key(self.signer,self.user_id,'other-account','chat','chat'), 'broken']
        with patch.object(application.graph_mail, 'request') as graph:
            for key in keys:
                self.assertEqual(self.client.get(self.path(key)).status_code, 400)
                self.assertEqual(self.client.post(self.path(key),data={'csrf_token':'test-token','text':'Hello'}).status_code, 400)
            graph.assert_not_called()

    def test_cursors_are_signed_and_bound_to_a_conversation_and_safe_origin(self):
        next_url = 'https://graph.microsoft.com/v1.0/chats/19:chat@thread.v2/messages?$skiptoken=next'
        with patch.object(application.graph_mail, 'request', side_effect=[{'value':[],'@odata.nextLink':next_url},{'value':[]}]) as graph:
            cursor = self.client.get(self.path()).json['next_cursor']
            self.assertEqual(self.client.get(self.path(),query_string={'cursor':cursor}).status_code, 200)
            self.assertIn('$skiptoken=next', graph.call_args.args[2])
        with patch.object(application.graph_mail, 'request') as graph:
            self.assertEqual(self.client.get(self.path(self.channel),query_string={'cursor':cursor}).status_code, 400)
            self.assertEqual(self.client.get(self.path(),query_string={'cursor':'broken'}).status_code, 400)
            graph.assert_not_called()
        for url in ('https://attacker.example/v1.0/chats/19:chat@thread.v2/messages','https://graph.microsoft.com/v1.0/users/other/messages'):
            with self.subTest(url=url), patch.object(application.graph_mail,'request',return_value={'value':[],'@odata.nextLink':url}) as graph:
                self.assertEqual(self.client.get(self.path()).status_code, 400); self.assertEqual(graph.call_count, 1)

    def test_replies_read_and_send_to_the_selected_thread_with_csrf(self):
        with patch.object(application.graph_mail, 'request', return_value={'value':[]}) as graph:
            self.assertEqual(self.client.get(self.path(self.channel),query_string={'reply':'123'}).status_code, 200)
            self.assertTrue(graph.call_args.args[2].endswith('/messages/123/replies'))
            self.assertEqual(self.client.post(self.path(self.channel),data={'csrf_token':'test-token','text':'Hello <Alex>','reply':'123'}).json, {'sent':True})
            self.assertEqual(graph.call_args.args[1], 'POST'); self.assertTrue(graph.call_args.args[2].endswith('/messages/123/replies'))
            self.assertEqual(graph.call_args.kwargs['payload']['body'], {'contentType':'text','content':'Hello <Alex>'})
            count = graph.call_count
            self.assertEqual(self.client.post(self.path(),data={'text':'No CSRF'}).status_code, 400)
            self.assertEqual(self.client.post(self.path(),data={'csrf_token':'test-token','text':'x'*4097}).status_code, 400)
            self.assertEqual(self.client.get(self.path(),query_string={'reply':'123'}).status_code, 400)
            self.assertEqual(graph.call_count, count)

    def test_refresh_keeps_tokens_in_the_database(self):
        self.config['token']['expires_at'] = 0
        with application.app.app_context(): application.save_integration(self.user_id,'teams',self.config)
        refreshed = Mock(); refreshed.json.return_value = {'access_token':'refreshed','expires_in':3600}
        with patch.object(application.requests,'post',return_value=refreshed) as exchange, patch.object(application.graph_mail,'request',return_value={'value':[]}) as graph:
            self.assertEqual(self.client.get(self.path()).status_code, 200)
            self.assertEqual(exchange.call_args.kwargs['data']['grant_type'], 'refresh_token'); self.assertEqual(graph.call_args.args[0], 'refreshed')
        with application.app.app_context(): saved = application.get_integration(self.user_id,'teams')['token']
        self.assertEqual(saved['access_token'],'refreshed'); self.assertEqual(saved['refresh_token'],'private-refresh')

    def test_denials_and_disconnect_are_clear_and_do_not_remove_outlook(self):
        forbidden = requests.Response(); forbidden.status_code = 403
        with patch.object(application.graph_mail,'request',side_effect=requests.HTTPError(response=forbidden)):
            response = self.client.get(self.path()); self.assertEqual(response.status_code,403); self.assertIn('administrator',response.json['error'])
        with application.app.app_context(): application.save_integration(self.user_id,'email:microsoft:work',{'kind':'microsoft','email':'work@example.com'})
        self.assertEqual(self.client.post('/integrations/teams/disconnect',data={'csrf_token':'test-token'}).status_code,302)
        self.assertEqual(self.client.get(self.path()).status_code,409)
        with application.app.app_context(): self.assertIsNotNone(application.get_integration(self.user_id,'email:microsoft:work'))
        self.assertEqual(application.app.test_client().get('/api/integrations/teams/conversations').status_code,302)

    def test_oauth_callback_belongs_to_the_current_user_and_does_not_request_mail(self):
        with patch.dict(application.app.config,{'MICROSOFT_CLIENT_ID':'client','MICROSOFT_CLIENT_SECRET':'secret','MICROSOFT_TEAMS_REDIRECT_URI':None}), patch.object(application.teams_oauth,'authorize_redirect',return_value=application.redirect('https://login.microsoftonline.com/')) as begin:
            self.assertEqual(self.client.get('/integrations/teams/connect').status_code,302)
            self.assertTrue(begin.call_args.args[0].endswith('/auth/teams/callback'))
        with patch.object(application.teams_oauth,'authorize_access_token',return_value={'access_token':'oauth-private'}) as exchange, patch.object(application.graph_mail,'request',return_value={'id':'new-account','displayName':'New account'}):
            self.assertEqual(self.client.get('/auth/teams/callback').status_code,302)
            self.assertEqual(self.client.get('/auth/teams/callback').status_code,400); self.assertEqual(exchange.call_count,1)
        self.assertIn('ChannelMessage.Read.All',graph_teams.SCOPES); self.assertNotIn('Mail.',graph_teams.SCOPES)


if __name__ == '__main__': unittest.main()
