"""Smart email controls and account isolation using local fixtures."""
import base64
import hashlib
import json
from email import policy
from email.parser import BytesParser
from unittest.mock import Mock, patch

import app as a
import email_providers
import graph_mail
from test_integrations import IntegrationFixture
from test_accessibility import PageMarkup


class MailFeatureTests(IntegrationFixture):
    def setUp(self):
        super().setUp()
        self.login()
        with a.app.app_context():
            a.store_google_token(self.user_id, {'access_token':'primary-token','expires_at':a.time.time()+3600})

    def payload(self, sender='no-reply@example.com', reply_to='', identifier='sample', text='Your verification code is 012345'):
        return {'id':identifier,'threadId':'thread','labelIds':['INBOX'],'snippet':text,'internalDate':'123',
            'payload':{'headers':[{'name':'From','value':sender},{'name':'Reply-To','value':reply_to},{'name':'Subject','value':'Verification code'}],
                       'mimeType':'text/plain','body':{'data':base64.urlsafe_b64encode(text.encode()).decode()}}}

    def save_gmail(self, email='second@example.com', token='second-token'):
        identifier=hashlib.sha256(email.encode()).hexdigest()[:12]
        key='email:gmail:'+identifier
        account={'key':key,'kind':'gmail','email':email,'config':{'kind':'gmail','name':'Gmail','email':email,'account_id':identifier,
                'token':{'access_token':token,'refresh_token':'refresh-'+token,'expires_at':a.time.time()+3600}}}
        with a.app.app_context():a.save_integration(self.user_id,key,account['config'])
        return account

    def gmail_status_response(self, url, **kwargs):
        response = Mock()
        identifier = url.rsplit('/', 1)[-1]
        response.json.return_value = {'id':identifier, 'labelIds':['INBOX'], 'messagesUnread':2, 'messagesTotal':1}
        return response

    def test_gmail_status_syncs_both_directions_without_extending_metadata_ttl(self):
        metadata = a.gmail_metadata_from_payload(self.payload(), 'sample')
        metadata.update(unread=True, label_ids=['INBOX','UNREAD','STARRED'])
        with a.app.app_context():
            a.gmail_cache_put(self.user_id, 'sample', metadata=metadata, body={'text':'Keep this body'})
            db=a.get_db()
            db.execute('UPDATE gmail_cache SET metadata_at=123 WHERE user_id=?', (self.user_id,))
            db.commit()
        with patch.object(a.google_requests, 'get', side_effect=self.gmail_status_response):
            response=self.post_form('/api/mail/gmail/status', {'message_ids':['sample','sample']})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['messages'],[{'id':'sample','unread':False}])
        self.assertEqual(response.json['counts']['inbox'],2)
        def unread(url, **kwargs):
            result=self.gmail_status_response(url, **kwargs)
            result.json.return_value['labelIds'].append('UNREAD')
            return result
        with patch.object(a.google_requests, 'get', side_effect=unread):
            response=self.post_form('/api/mail/gmail/status', {'message_ids':'sample'})
        self.assertTrue(response.json['messages'][0]['unread'])
        with a.app.app_context():
            cached=a.get_db().execute('SELECT * FROM gmail_cache WHERE user_id=?', (self.user_id,)).fetchone()
            self.assertEqual(cached['metadata_at'],123)
            self.assertEqual(json.loads(cached['body']),{'text':'Keep this body'})
            self.assertEqual(set(json.loads(cached['metadata'])['label_ids']),{'INBOX','UNREAD','STARRED'})

    def test_gmail_status_uses_selected_account_and_rejects_foreign_or_invalid_ids(self):
        second=self.save_gmail()
        identifier=a.gmail_message_key(second,'sample')
        with patch.object(a.google_requests, 'get', side_effect=self.gmail_status_response) as fetch:
            response=self.post_form('/api/mail/gmail/status', {'account':second['key'],'message_ids':identifier})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['messages'][0]['id'],identifier)
        for call in fetch.call_args_list:
            self.assertEqual(call.kwargs['headers']['Authorization'],'Bearer second-token')
        self.assertTrue(any(call.args[0].endswith('/messages/sample') for call in fetch.call_args_list))
        with patch.object(a.google_requests, 'get') as fetch:
            for data in ({'account':second['key'],'message_ids':'sample'}, {'message_ids':identifier}, {'message_ids':'../invalid'}, {'message_ids':[]}, {'message_ids':[str(i) for i in range(51)]}):
                self.assertEqual(self.post_form('/api/mail/gmail/status',{'account':'gmail',**data}).status_code,400)
            self.assertEqual(self.client.post('/api/mail/gmail/status',data={'message_ids':'sample'}).status_code,400)
        fetch.assert_not_called()

    def test_gmail_status_does_not_overwrite_a_local_action_completed_during_fetch(self):
        metadata=a.gmail_metadata_from_payload(self.payload(),'sample')
        metadata.update(unread=True,label_ids=['INBOX','UNREAD'])
        def concurrent_action(url, **kwargs):
            response=self.gmail_status_response(url,**kwargs)
            if '/messages/' in url:
                metadata.update(unread=False,label_ids=['INBOX'])
                with a.app.app_context():a.gmail_cache_put(self.user_id,'sample',metadata=metadata)
                response.json.return_value['labelIds'].append('UNREAD')
            return response
        for original_unread in (True, False):
            with self.subTest(original_unread=original_unread):
                metadata.update(unread=original_unread,label_ids=['INBOX','UNREAD'] if original_unread else ['INBOX'])
                with a.app.app_context():
                    a.gmail_cache_put(self.user_id,'sample',metadata=metadata)
                    a.get_db().execute('UPDATE gmail_cache SET metadata_at=123 WHERE user_id=?', (self.user_id,))
                    a.get_db().commit()
                with patch.object(a.google_requests,'get',side_effect=concurrent_action):
                    response=self.post_form('/api/mail/gmail/status',{'message_ids':'sample'})
                self.assertEqual(response.json['messages'],[{'id':'sample','unread':False}])
                with a.app.app_context():self.assertFalse(a.gmail_cache_get(self.user_id,'sample')['unread'])

    def test_gmail_status_errors_preserve_cached_status_and_missing_messages_are_skipped(self):
        metadata=a.gmail_metadata_from_payload(self.payload(),'sample')
        metadata.update(unread=True,label_ids=['INBOX','UNREAD'])
        with a.app.app_context():a.gmail_cache_put(self.user_id,'sample',metadata=metadata)
        for status in (401,403,429,500):
            error=a.requests.HTTPError(response=Mock(status_code=status))
            with patch.object(a.google_requests,'get',side_effect=error):
                response=self.post_form('/api/mail/gmail/status',{'message_ids':['sample','other']})
            self.assertEqual(response.status_code,502)
            with a.app.app_context():self.assertTrue(a.gmail_cache_get(self.user_id,'sample')['unread'])
        def missing(url, **kwargs):
            if '/messages/' in url:raise a.requests.HTTPError(response=Mock(status_code=404))
            return self.gmail_status_response(url,**kwargs)
        with patch.object(a.google_requests,'get',side_effect=missing):
            response=self.post_form('/api/mail/gmail/status',{'message_ids':'sample'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['messages'],[])
        malformed=Mock(); malformed.json.return_value={'id':'sample','labelIds':'UNREAD'}
        with patch.object(a.google_requests,'get',return_value=malformed):
            self.assertEqual(self.post_form('/api/mail/gmail/status',{'message_ids':'sample'}).status_code,502)
        with a.app.app_context():self.assertTrue(a.gmail_cache_get(self.user_id,'sample')['unread'])

    def test_no_reply_variants_and_usable_reply_to(self):
        for address in ('noreply@example.com','NO-REPLY@example.com','no_reply+123@example.com','do.not.reply@example.com','DoNotReply@example.com','alerts-no-reply@example.com','noreply123@example.com'):
            with self.subTest(address=address):
                info=a.email_reply_info({'email':address})
                self.assertTrue(info['is_no_reply']);self.assertFalse(info['can_reply'])
        for address in ('support@example.com','notifications@example.com','jane.noreplyson@example.com'):
            self.assertTrue(a.email_reply_info({'email':address})['can_reply'])
        self.assertFalse(a.email_reply_info({'email':'invalid'})['can_reply'])
        info=a.email_reply_info({'email':'noreply@example.com','reply_to':'noreply@example.com, Support <support@example.com>'})
        self.assertTrue(info['can_reply']);self.assertFalse(info['is_no_reply']);self.assertEqual(info['reply_address'],'support@example.com')

    def test_otp_detection_preserves_zeroes_and_ignores_ambiguous_or_unrelated_numbers(self):
        examples=[('Login code','Your verification code is 012345','012345'),
                  ('Welcome','Your OTP: 123 456','123456'),('Welcome','123456 is your security code','123456'),
                  ('Welcome','Your one-time password: AB12CD','AB12CD'),('Your verification code','012345\nExpires in 10 minutes','012345'),
                  ('Receipt','Order 123456. Total 2026.00',None),('Security update','Call support at 1234567890',None),
                  ('Codes','OTP: 123456. OTP: 654321',None),('Re: Sign in','Thank you.\nOn Tuesday, Sender wrote:\nOTP: 123456',None)]
        for subject,text,expected in examples:
            with self.subTest(text=text):self.assertEqual(a.extract_otp_code(subject,text),expected)

    def test_no_reply_buttons_are_disabled_in_both_readers_and_otp_is_copyable(self):
        payload=self.payload()
        payload['labelIds'].append('UNREAD')
        with a.app.app_context():a.gmail_cache_put(self.user_id,'sample',metadata=a.gmail_metadata_from_payload(payload,'sample'),body={'text':'Your verification code is 012345'})
        for suffix in ('','?pane=1'):
            response=self.client.get('/message/sample'+suffix)
            elements=PageMarkup(response.text).elements
            reply=next(attrs for _,attrs,_ in elements if 'data-email-reply' in attrs)
            self.assertIn('disabled',reply)
            self.assertEqual(reply['aria-describedby'],'reply-unavailable-sample')
            self.assertIn(b'data-copy-code="012345"',response.data)
            self.assertIn(b'Replies are disabled',response.data)
            trigger=next(attrs for _,attrs,_ in elements if attrs.get('id')=='reply-tooltip-trigger-sample')
            self.assertEqual(trigger['tabindex'],'0')
            self.assertIn(b'<m3e-tooltip anchor="reply-tooltip-trigger-sample"',response.data)
            self.assertIn(b'data-mark-email-read="true"',response.data)

    def test_no_reply_post_is_blocked_for_all_mail_providers(self):
        for kind in ('gmail','imap','microsoft'):
            config={'kind':kind,'account_id':'a'*12,'email':'mail@example.com','name':kind,'folders':{'inbox':'INBOX'},'token':{'access_token':'test','expires_at':a.time.time()+3600}}
            key='gmail' if kind=='gmail' else 'email:'+kind+':'+'a'*12
            if kind!='gmail':
                with a.app.app_context():a.save_integration(self.user_id,key,config)
            identifier='sample' if kind=='gmail' else email_providers.make_id(config,'inbox','123',7) if kind=='imap' else graph_mail.message_id(config,'sample')
            original={**a.gmail_metadata_from_payload(self.payload(),'sample'),'id':identifier,'body':{'text':'Notification'}}
            with patch.object(a,'fetch_email_message',return_value=original),patch.object(a,'send_gmail_message') as gmail,patch.object(email_providers,'send_message') as smtp,patch.object(graph_mail,'reply_message') as outlook:
                response=self.post_form('/compose',{'account':key,'reply_id':identifier,'to':'someone@example.com','subject':'Re: notification','body':'Reply'})
            gmail.assert_not_called();smtp.assert_not_called();outlook.assert_not_called()
            self.assertIn(b'Replies are disabled',response.data)

    def test_cached_inbox_is_classified_without_loading_email_bodies(self):
        metadata=a.gmail_metadata_from_payload(self.payload(),'sample')
        metadata.pop('can_reply');metadata.pop('is_no_reply');metadata.pop('otp_code')
        with a.app.app_context():a.gmail_cache_put(self.user_id,'sample',metadata=metadata)
        with patch.object(a.google_requests,'get') as network:
            response=self.client.get('/inbox')
        network.assert_not_called()
        self.assertIn(b'data-no-reply="true"',response.data)
        self.assertIn(b'data-copy-code="012345"',response.data)
        self.assertIn(b'id="mail-sort"',response.data)

    def test_google_connect_preserves_centromail_identity_and_reuses_accounts(self):
        previous={key:a.app.config[key] for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REDIRECT_URI')}
        self.addCleanup(a.app.config.update,previous)
        a.app.config.update(GOOGLE_CLIENT_ID='client',GOOGLE_CLIENT_SECRET='secret',GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback')
        for _ in range(2):
            with patch.object(a.google,'authorize_redirect',return_value=a.redirect('/google')) as start:
                self.client.get('/auth/google?connect=1')
                self.assertIn('select_account',start.call_args.kwargs['prompt'])
            token={'access_token':'second-token','expires_at':a.time.time()+3600,'userinfo':{'email':'second@example.com','email_verified':True,'name':'Second'}}
            with patch.object(a.google,'authorize_access_token',return_value=token):response=self.client.get('/auth/google/callback')
            self.assertEqual(response.status_code,302)
            with self.client.session_transaction() as session:self.assertEqual(session['user_id'],self.user_id)
        with a.app.app_context():
            accounts=a.email_accounts(a.find_user('integrations@example.com'))
            self.assertEqual(len(accounts),2)
            self.assertIsNone(a.find_user('second@example.com'))

    def test_google_connect_keeps_intent_when_switching_localhost(self):
        previous={key:a.app.config[key] for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REDIRECT_URI')}
        self.addCleanup(a.app.config.update,previous)
        a.app.config.update(GOOGLE_CLIENT_ID='client',GOOGLE_CLIENT_SECRET='secret',GOOGLE_REDIRECT_URI='http://127.0.0.1/auth/google/callback')
        with patch.object(a.google,'authorize_redirect') as start:
            response=self.client.get('/auth/google?connect=1')
            self.assertEqual(response.location,'http://127.0.0.1/auth/google?connect=1')
            response=self.client.get(response.location)
        start.assert_not_called()
        self.assertTrue(response.location.endswith('/login'))
        with self.client.session_transaction() as session:self.assertEqual(session['user_id'],self.user_id)

    def test_gmail_refresh_tokens_and_counts_are_account_bound(self):
        second=self.save_gmail();third=self.save_gmail('third@example.com','third-token')
        with a.app.app_context():
            second['config']['token']['expires_at']=0
            a.save_integration(self.user_id,second['key'],second['config'])
        refreshed=Mock();refreshed.json.return_value={'access_token':'refreshed-second','expires_in':3600}
        with a.app.test_request_context('/inbox?account='+second['key']),patch.object(a.google_requests,'post',return_value=refreshed) as refresh:
            self.assertEqual(a.get_gmail_access_token(a.find_user('integrations@example.com')),'refreshed-second')
            self.assertEqual(refresh.call_args.kwargs['data']['refresh_token'],'refresh-second-token')
            self.assertEqual(a.get_integration(self.user_id,third['key'])['token']['access_token'],'third-token')
            self.assertEqual(a.get_google_token(a.find_user('integrations@example.com'))['access_token'],'primary-token')
        for key,expected in [('gmail',2),(second['key'],5),(third['key'],8)]:
            count=Mock();count.json.return_value={'messagesUnread':expected,'messagesTotal':1}
            with patch.object(a.google_requests,'get',return_value=count):
                self.assertEqual(self.client.get('/api/mail/counts',query_string={'account':key}).json['inbox'],expected)
        with patch.object(a.google_requests,'get') as fetch:
            for key,expected in [('gmail',2),(second['key'],5),(third['key'],8)]:
                self.assertEqual(self.client.get('/api/mail/counts',query_string={'account':key}).json['inbox'],expected)
        fetch.assert_not_called()

    def test_gmail_caches_tokens_and_actions_are_account_bound(self):
        second=self.save_gmail();third=self.save_gmail('third@example.com','third-token')
        for account,token in [(second,'second-token'),(third,'third-token')]:
            listing=Mock();listing.json.return_value={'messages':[{'id':'same'}]}
            metadata=a.gmail_metadata_from_payload(self.payload(sender='support@example.com',identifier='same'),'same')
            with patch.object(a.google_requests,'get',return_value=listing) as fetch,patch.object(a,'_fetch_gmail_detail',return_value=metadata):
                response=self.client.get('/api/mail/messages',query_string={'account':account['key']})
            self.assertEqual(response.status_code,200)
            self.assertEqual(fetch.call_args.kwargs['headers']['Authorization'],'Bearer '+token)
            self.assertIn(a.gmail_message_key(account,'same'),response.json['html'])
        with patch.object(a.google_requests,'get') as fetch,patch.object(a,'_fetch_gmail_detail') as detail:
            self.client.get('/api/mail/messages',query_string={'account':second['key']})
        fetch.assert_not_called();detail.assert_not_called()
        with a.app.test_request_context('/inbox?account=gmail'):
            self.assertEqual(a.cached_mail_preview(a.find_user('integrations@example.com'),'inbox'),[])
        identifier=a.gmail_message_key(second,'same')
        with patch.object(a.google_requests,'post',return_value=Mock()) as change:
            self.post_form('/api/mail/action',{'account':second['key'],'action':'star','message_ids':identifier})
        self.assertEqual(change.call_args.kwargs['json']['ids'],['same'])
        with patch.object(a.google_requests,'post') as change:
            self.post_form('/api/mail/action',{'account':second['key'],'action':'star','message_ids':a.gmail_message_key(third,'same')})
        change.assert_not_called()

    def test_sending_and_disconnect_use_only_selected_gmail(self):
        second=self.save_gmail();third=self.save_gmail('third@example.com','third-token')
        with patch.object(a.google_requests,'post',return_value=Mock()) as send:
            self.post_form('/compose',{'account':second['key'],'to':'friend@example.com','subject':'Hello','body':'Message'})
        self.assertEqual(send.call_args.kwargs['headers']['Authorization'],'Bearer second-token')
        raw=send.call_args.kwargs['json']['raw']
        message=BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
        self.assertEqual(message['From'],'second@example.com')
        with a.app.app_context():
            for account in (second,third):a.gmail_cache_put(self.user_id,a.gmail_message_key(account,'same'),metadata={'id':'same'})
        self.post_form('/integrations/email/disconnect',{'account':second['key']})
        with a.app.app_context():
            self.assertIsNone(a.gmail_cache_get(self.user_id,a.gmail_message_key(second,'same')))
            self.assertIsNotNone(a.gmail_cache_get(self.user_id,a.gmail_message_key(third,'same')))

    def test_apps_are_rendered_without_fetching_and_whatsapp_feed_is_available(self):
        with a.app.app_context():
            a.save_integration(self.user_id,'telegram',{'stage':'connected','session':'private-session','account':{'username':'tester'}})
            a.save_integration(self.user_id,'discord',{'bot_token':'private-token','channel_name':'general'})
            a.save_integration(self.user_id,'whatsapp',{'access_token':'private-whatsapp','display_phone_number':'+1234567890'})
        with patch.object(a,'telegram_snapshot') as telegram,patch.object(a,'discord_recent_messages') as discord:
            response=self.client.get('/inbox')
        telegram.assert_not_called();discord.assert_not_called()
        self.assertIn(b'data-app-provider="telegram"',response.data)
        self.assertIn(b'data-app-provider="discord"',response.data)
        self.assertNotIn(b'private-token',response.data);self.assertNotIn(b'private-session',response.data)
        with patch.object(a,'whatsapp_recent_messages',return_value=[{'text':'Hello','sender':'Friend','time':'Today'}]):
            self.assertEqual(self.client.get('/api/integrations/whatsapp/messages').json['messages'][0]['text'],'Hello')
