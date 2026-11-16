"""Mail protocol and account routing checks without contacting providers."""
import json
import unittest
from unittest.mock import Mock, patch
import email_providers
import graph_mail
import app as application
import test_integrations as fixtures


class MailProtocolTests(unittest.TestCase):
    config={'account_id':'a'*12,'email':'mail@example.com','password':'test-password','imap_host':'imap.example.com','imap_port':993,'imap_security':'ssl','smtp_host':'smtp.example.com','smtp_port':587,'smtp_security':'starttls','folders':{'inbox':'INBOX','sent':'Sent','trash':'Trash','archive':'Archive'}}

    def test_imap_lazy_page_fetches_only_25_headers_and_preserves_flags(self):
        with patch.object(email_providers,'imap_connect') as connect:
            client=connect.return_value.__enter__.return_value
            client.select.return_value=('OK',[b'100']);client.response.return_value=('UIDVALIDITY',[b'123'])
            def uid(command,*args):
                if command=='SEARCH':return 'OK',[b' '.join(str(n).encode() for n in range(1,101))]
                rows=[(f'1 (UID {n} FLAGS (\\Flagged) BODY[HEADER] {{60}}'.encode(), b'From: Alice <alice@example.com>\r\nSubject: Hello\r\n\r\n') for n in range(100,75,-1)]
                return 'OK',rows
            client.uid.side_effect=uid
            messages,cursor,total=email_providers.list_messages(self.config)
            self.assertEqual((len(messages),cursor,total),(25,'76',100))
            fetch=client.uid.call_args_list[1]
            self.assertEqual(len(fetch.args[1].split(',')),25)
            self.assertIn('BODY.PEEK',fetch.args[2])
            self.assertIn('UNREAD',messages[0]['labelIds']);self.assertIn('STARRED',messages[0]['labelIds'])
            self.assertEqual(messages[0]['id'],email_providers.make_id(self.config,'inbox','123',100))

    def test_imap_rejects_other_accounts_and_changed_uidvalidity(self):
        identifier=email_providers.make_id(self.config,'inbox','123',7)
        self.assertEqual(email_providers.parse_id(self.config,identifier,'123'),'7')
        for value in ('imap-'+'b'*12+'-123-7',identifier):
            with self.assertRaises(ValueError):email_providers.parse_id(self.config,value,'999')
        with self.assertRaises(ValueError):email_providers.parse_id(self.config,identifier,'123','sent')
        self.assertEqual(email_providers.parse_id(self.config,identifier,'123','starred'),'7')

    def test_imap_move_fallback_never_expunges_unrelated_messages(self):
        with patch.object(email_providers,'imap_connect') as connect:
            client=connect.return_value.__enter__.return_value
            client.capabilities=();client.select.return_value=('OK',[b'100']);client.response.return_value=('UIDVALIDITY',[b'123']);client.uid.return_value=('OK',[])
            email_providers.change_messages(self.config,[email_providers.make_id(self.config,'inbox','123',7)],'trash')
            self.assertEqual([call.args[0] for call in client.uid.call_args_list],['COPY','STORE'])
            client.expunge.assert_not_called()

    def test_imap_tls_and_smtp_starttls_keep_certificate_verification(self):
        with patch.object(email_providers.imaplib,'IMAP4_SSL') as connect:
            email_providers.imap_connect(self.config)
            self.assertTrue(connect.call_args.kwargs['ssl_context'].check_hostname)
        with patch.object(email_providers.smtplib,'SMTP') as connect:
            email_providers.smtp_connect(self.config)
            self.assertTrue(connect.return_value.starttls.call_args.kwargs['context'].check_hostname)
            connect.return_value.login.assert_called_once_with(self.config['email'],self.config['password'])

    def test_microsoft_ids_and_cursor_are_bound_to_the_account_and_graph(self):
        identifier=graph_mail.message_id(self.config,'message+/=')
        self.assertEqual(graph_mail.raw_id(self.config,identifier),'message%2B%2F%3D')
        with self.assertRaises(ValueError):graph_mail.raw_id({'account_id':'b'*12},identifier)
        with self.assertRaises(ValueError):graph_mail.list_messages('test',self.config,'inbox',cursor=graph_mail.encode('https://127.0.0.1/v1.0/me/mailFolders/inbox/messages'))
        with patch.object(graph_mail,'request',return_value={'value':[]}) as request:
            graph_mail.list_messages('test',self.config,'inbox')
            self.assertEqual(request.call_args.kwargs['params']['$top'],25)

    def test_sent_copy_failure_reports_delivery_success_without_retry(self):
        from email.message import EmailMessage
        message=EmailMessage();message['From']=self.config['email'];message['To']='recipient@example.com';message.set_content('Hello')
        with patch.object(email_providers,'smtp_connect') as smtp,patch.object(email_providers,'imap_connect') as imap:
            smtp.return_value.__enter__.return_value.send_message.return_value={}
            imap.return_value.__enter__.return_value.append.return_value=('NO',[])
            warning=email_providers.send_message(self.config,message)
            self.assertIn('Do not send it again',warning)
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
            self.assertIn('Message-ID',message);self.assertIn('Date',message)

    def test_microsoft_starred_search_filters_each_lazy_page(self):
        items=[{'id':'1','subject':'Starred','flag':{'flagStatus':'flagged'}},{'id':'2','subject':'Other'}]
        with patch.object(graph_mail,'request',return_value={'value':items}) as request:
            messages,_,_=graph_mail.list_messages('test',self.config,'starred',query='invoice')
            self.assertEqual(len(messages),1)
            self.assertNotIn('$filter',request.call_args.kwargs['params'])
        with patch.object(graph_mail,'request',return_value={'value':[]}) as request:
            graph_mail.list_messages('test',self.config,'starred')
            self.assertTrue(request.call_args.kwargs['params']['$filter'].startswith('receivedDateTime'))

    def test_microsoft_batch_rejects_other_account_before_any_changes(self):
        identifiers=[graph_mail.message_id(self.config,'valid'),graph_mail.message_id({'account_id':'b'*12},'other')]
        with patch.object(graph_mail,'request') as request:
            with self.assertRaises(ValueError):graph_mail.change_messages('test',self.config,identifiers,'trash')
            request.assert_not_called()

    def test_preset_remote_connections_require_verified_tls(self):
        for preset in email_providers.PROVIDERS:
            for field in ('imap_security','smtp_security'):
                self.assertIn(preset[field],{'ssl','starttls'})
            if preset['key']!='custom':
                email_providers.validate_host(preset['imap_host']);email_providers.validate_host(preset['smtp_host'])

    def test_bridge_certificate_adds_trust_without_replacing_system_roots(self):
        with patch.dict(email_providers.os.environ,{'CENTROMAIL_MAIL_CA_FILE':'bridge.pem'}),patch.object(email_providers.ssl,'create_default_context') as create:
            context=email_providers.tls_context()
            create.assert_called_once_with()
            context.load_verify_locations.assert_called_once_with(cafile='bridge.pem')

    def test_custom_smtp_credentials_and_server_saved_sent(self):
        with patch.object(email_providers.smtplib,'SMTP') as smtp:
            email_providers.smtp_connect({**self.config,'smtp_username':'alternate-login','smtp_password':'alternate-password'})
            smtp.return_value.login.assert_called_once_with('alternate-login','alternate-password')
        with patch.object(email_providers,'smtp_connect') as smtp,patch.object(email_providers,'imap_connect') as imap:
            from email.message import EmailMessage
            smtp.return_value.__enter__.return_value.send_message.return_value={}
            email_providers.send_message({**self.config,'save_sent':False},EmailMessage())
            imap.assert_not_called()


class EmailRouteTests(fixtures.IntegrationFixture):
    def save_account(self,kind='imap'):
        key='email:'+kind+':'+'a'*12
        config={**MailProtocolTests.config,'name':'Test email','kind':kind}
        if kind=='microsoft':config['token']={'access_token':'test','expires_at':application.time.time()+3600}
        with application.app.app_context():application.save_integration(self.user_id,key,config)
        return key

    def test_imap_account_connects_without_exposing_credentials_in_html(self):
        with patch.object(email_providers,'imap_connect') as imap,patch.object(email_providers,'smtp_connect') as smtp,patch.object(email_providers,'discover_folders',return_value={'inbox':'INBOX'}):
            response=self.post_form('/integrations/email/connect',{'provider':'fastmail','email':'my@example.com','password':'very-private-app-password'})
        self.assertEqual(response.status_code,200)
        self.assertIn(b'my@example.com',response.data)
        self.assertNotIn(b'very-private-app-password',response.data)
        with application.app.app_context():
            account=application.email_accounts(application.find_user('integrations@example.com'))[0]
        self.assertEqual(account['config']['imap_host'],'imap.fastmail.com')
        self.assertEqual(account['config']['password'],'very-private-app-password')

    def test_imap_inbox_routes_list_reader_send_and_actions_to_selected_account(self):
        self.login();key=self.save_account();identifier=email_providers.make_id(MailProtocolTests.config,'inbox','123',7)
        metadata={'id':identifier,'labelIds':['INBOX','UNREAD'],'payload':{'headers':[{'name':'From','value':'Alice <alice@example.com>'},{'name':'Subject','value':'Test'}]}}
        with patch.object(email_providers,'list_messages',return_value=([metadata],None,1)) as imap,patch.object(application.google_requests,'get') as google:
            response=self.client.get('/api/mail/messages',query_string={'account':key})
            self.assertEqual(response.status_code,200);self.assertIn(b'Alice',response.data);google.assert_not_called()
        body={**metadata,'payload':{**metadata['payload'],'mimeType':'text/plain','body':{'data':'SGVsbG8='}}}
        with patch.object(email_providers,'read_message',return_value=body):
            response=self.client.get('/message/'+identifier,query_string={'account':key})
            self.assertEqual(response.status_code,200);self.assertIn(b'Hello',response.data)
        with patch.object(email_providers,'change_messages') as change:
            response=self.post_form('/api/mail/action',{'account':key,'folder':'inbox','action':'star','message_ids':identifier})
            self.assertEqual(response.status_code,200);change.assert_called_once()
        with application.app.app_context():
            self.assertIn('STARRED',application.gmail_cache_get(self.user_id,identifier)['label_ids'])
        with patch.object(email_providers,'send_message',return_value=None) as send:
            response=self.post_form('/compose',{'account':key,'to':'recipient@example.com','subject':'Hello','body':'Message'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(send.call_args.args[1]['From'],'mail@example.com')
        self.assertEqual(self.client.get('/inbox?account=email:imap:unknown').status_code,404)

    def test_disconnect_removes_only_the_selected_accounts_cache(self):
        self.login();key=self.save_account()
        with application.app.app_context():
            application.gmail_cache_put(self.user_id,'imap-'+'a'*12+'-123-7',metadata={'unread':False,'starred':False})
            application.gmail_cache_put(self.user_id,'gmail-message',metadata={'unread':False,'starred':False})
        self.post_form('/integrations/email/disconnect',{'account':key})
        with application.app.app_context():
            self.assertIsNone(application.get_integration(self.user_id,key))
            self.assertIsNotNone(application.gmail_cache_get(self.user_id,'gmail-message'))
            self.assertIsNone(application.gmail_cache_get(self.user_id,'imap-'+'a'*12+'-123-7'))

    def test_compose_rejects_multiline_subject_without_contacting_provider(self):
        self.login();key=self.save_account()
        with patch.object(email_providers,'send_message') as send:
            response=self.post_form('/compose',{'account':key,'to':'recipient@example.com','subject':'Hello\r\nBcc: other@example.com','body':'Test'})
            self.assertEqual(response.status_code,200);send.assert_not_called()
            self.assertIn(b'subject must be a single line',response.data)

    def test_microsoft_callback_requires_state_and_saves_only_to_signed_in_user(self):
        self.login()
        self.assertEqual(self.client.get('/auth/microsoft/callback').status_code,400)
        with self.client.session_transaction() as session:session['microsoft_connect_user']=self.user_id
        with patch.object(application.microsoft,'authorize_access_token',return_value={'access_token':'test','expires_at':application.time.time()+3600}),patch.object(graph_mail,'request',return_value={'mail':'outlook@example.com'}):
            response=self.client.get('/auth/microsoft/callback')
        self.assertEqual(response.status_code,302)
        with application.app.app_context():
            accounts=application.email_accounts(application.find_user('integrations@example.com'))
            self.assertEqual(accounts[0]['kind'],'microsoft')
            self.assertEqual(accounts[0]['email'],'outlook@example.com')

if __name__=='__main__':unittest.main()
