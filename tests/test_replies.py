"""Reply routing and conversation headers, without sending live email."""
import base64
from email import policy
from email.parser import BytesParser
from unittest.mock import Mock, patch

import app as application
import email_providers
import graph_mail
from test_integrations import IntegrationFixture
from test_accessibility import PageMarkup


class ReplyTests(IntegrationFixture):
    def setUp(self):
        super().setUp()
        self.login()
        self.payload = {
            'id': 'original', 'threadId': 'thread-123',
            'payload': {'headers': [
                {'name': 'From', 'value': 'Sender <sender@example.com>'},
                {'name': 'Reply-To', 'value': 'Support <support@example.com>'},
                {'name': 'To', 'value': 'integrations@example.com'},
                {'name': 'Subject', 'value': 'Re: Project update'},
                {'name': 'Message-ID', 'value': '<original@example.com>'},
                {'name': 'References', 'value': '<first@example.com>'},
            ]},
        }
        self.draft = {'account': 'gmail', 'folder': 'inbox', 'reply_id': 'original',
                      'to': 'support@example.com', 'subject': 'Re: Project update', 'body': 'Thanks for the update.'}
        with application.app.app_context():
            application.store_google_token(self.user_id, {'access_token': 'test-token', 'expires_at': application.time.time() + 3600})
            application.gmail_cache_put(self.user_id, 'original',
                metadata=application.gmail_metadata_from_payload(self.payload, 'original'), body={'text': 'Original email.'})

    def save_mail_account(self, kind, account_id='a' * 12):
        key = 'email:' + kind + ':' + account_id
        config = {'kind': kind, 'account_id': account_id, 'email': 'mail@example.com',
                  'name': 'Work email', 'folders': {'inbox': 'INBOX', 'sent': 'Sent'},
                  'token': {'access_token': 'graph-token', 'expires_at': application.time.time() + 3600}}
        with application.app.app_context():
            application.save_integration(self.user_id, key, config)
        return key, config

    def test_reply_action_in_both_readers_uses_reply_to_and_keeps_subject(self):
        for query in ('', '?pane=1'):
            response = self.client.get('/message/original' + query)
            buttons = [attrs for tag, attrs, _ in PageMarkup(response.text).elements if 'data-email-reply' in attrs]
            self.assertEqual(len(buttons), 1)
            self.assertEqual(buttons[0]['data-reply-to'], 'support@example.com')
            self.assertEqual(buttons[0]['data-reply-subject'], 'Re: Project update')
            self.assertEqual(buttons[0]['data-reply-account'], 'gmail')
        # Sent mail replies go to the original recipient rather than ourselves.
        self.assertEqual(application.reply_address({'email': 'integrations@example.com', 'to': 'Friend <friend@example.com>'}, {'email': 'integrations@example.com'}), 'friend@example.com')
        self.assertEqual(application.reply_address({'reply_to': 'support@example.com, other@example.com'}, {'email': 'integrations@example.com'}), 'support@example.com')

    def test_gmail_reply_sends_thread_and_rfc_headers(self):
        with patch.object(application.google_requests, 'post', return_value=Mock()) as send:
            response = self.post_form('/compose', self.draft)
        self.assertEqual(response.status_code, 200)
        payload = send.call_args.kwargs['json']
        self.assertEqual(payload['threadId'], 'thread-123')
        message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(payload['raw'] + '=' * (-len(payload['raw']) % 4)))
        self.assertEqual(message['In-Reply-To'], '<original@example.com>')
        self.assertEqual(message['References'], '<first@example.com> <original@example.com>')
        self.assertEqual(message['To'], 'support@example.com')
        self.assertEqual(message['From'], 'integrations@example.com')
        self.assertEqual(message.get_content().strip(), self.draft['body'])

    def test_old_gmail_cache_refreshes_headers_before_reply(self):
        with application.app.app_context():
            application.gmail_cache_put(self.user_id, 'old', metadata={'id': 'old', 'email': 'sender@example.com'}, body={'text': 'Old cached email.'})
            user = application.find_user('integrations@example.com')
            response = Mock()
            response.json.return_value = self.payload
            with patch.object(application.google_requests, 'get', return_value=response) as fetch:
                original = application.fetch_gmail_message(user, 'old', for_reply=True)
            fetch.assert_called_once()
            self.assertEqual(original['message_id'], '<original@example.com>')
            self.assertEqual(original['thread_id'], 'thread-123')
            # The reader must refresh legacy metadata too, before prefilling Reply-To.
            application.gmail_cache_put(self.user_id, 'old', metadata={'id': 'old', 'email': 'sender@example.com'}, body={'text': 'Old cached email.'})
        with patch.object(application.google_requests, 'get', return_value=response):
            page = self.client.get('/message/old')
        self.assertIn(b'data-reply-to="support@example.com"', page.data)

    def test_imap_reply_uses_received_account_and_thread_headers(self):
        key, config = self.save_mail_account('imap')
        identifier = email_providers.make_id(config, 'inbox', '123', 7)
        payload = {**self.payload, 'id': identifier}
        with patch.object(email_providers, 'read_message', return_value=payload), patch.object(email_providers, 'send_message', return_value=None) as send, patch.object(application.google_requests, 'post') as google:
            response = self.post_form('/compose', {**self.draft, 'account': key, 'reply_id': identifier})
        self.assertEqual(response.status_code, 200)
        google.assert_not_called()
        message = send.call_args.args[1]
        self.assertEqual(message['From'], 'mail@example.com')
        self.assertEqual(message['In-Reply-To'], '<original@example.com>')
        self.assertEqual(message['References'], '<first@example.com> <original@example.com>')
        raw = b'From: Sender <sender@example.com>\r\nReply-To: support@example.com\r\nMessage-ID: <original@example.com>\r\nReferences: <first@example.com>\r\n\r\nHello'
        parsed = email_providers.message_payload(raw, b'', identifier, 'inbox')
        self.assertEqual(application.gmail_metadata_from_payload(parsed, identifier)['reply_to'], 'support@example.com')

    def test_microsoft_reply_uses_native_reply_endpoint(self):
        key, config = self.save_mail_account('microsoft')
        identifier = graph_mail.message_id(config, 'original/id')
        with patch.object(graph_mail, 'read_message', return_value={**self.payload, 'id': identifier}), patch.object(graph_mail, 'request') as send:
            response = self.post_form('/compose', {**self.draft, 'account': key, 'reply_id': identifier})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(send.call_args.args[:3], ('graph-token', 'POST', '/me/messages/original%2Fid/reply'))
        message = send.call_args.kwargs['payload']['message']
        self.assertEqual(message['body']['content'], self.draft['body'])
        self.assertEqual(message['toRecipients'][0]['emailAddress']['address'], 'support@example.com')

    def test_reply_cannot_read_or_send_from_a_different_account(self):
        key, config = self.save_mail_account('imap')
        _, other = self.save_mail_account('imap', 'b' * 12)
        identifier = email_providers.make_id(other, 'inbox', '123', 7)
        with patch.object(email_providers, 'read_message') as read, patch.object(email_providers, 'send_message') as send:
            response = self.post_form('/compose', {**self.draft, 'account': key, 'reply_id': identifier})
        read.assert_not_called()
        send.assert_not_called()
        self.assertIn(b'data-compose-draft', response.data)
        with patch.object(application.google_requests, 'get') as read, patch.object(application.google_requests, 'post') as send:
            self.post_form('/compose', {**self.draft, 'reply_id': identifier})
        read.assert_not_called()
        send.assert_not_called()

    def test_failed_reply_retains_draft_and_csrf_protection(self):
        self.assertEqual(self.client.post('/compose', data=self.draft).status_code, 400)
        with patch.object(application.google_requests, 'post', side_effect=application.requests.ConnectionError('offline')):
            response = self.post_form('/compose', {**self.draft, 'body': '<Keep this draft> & retry'})
        self.assertIn(b'data-compose-draft', response.data)
        self.assertIn(b'&lt;Keep this draft&gt; &amp; retry', response.data)
        self.assertIn(b'name="reply_id" value="original"', response.data)
        self.assertIn(b'could not send', response.data)

    def test_received_thread_headers_cannot_inject_new_headers(self):
        message = application.EmailMessage()
        application.add_reply_headers(message, {'message_id': '<original@example.com>\r\nBcc: hidden@example.com', 'references': '<first@example.com>\r\nCc: hidden@example.com'})
        self.assertEqual(message['In-Reply-To'], '<original@example.com>')
        self.assertEqual(message['References'], '<first@example.com> <original@example.com>')
        self.assertNotIn('Bcc', message)
        self.assertNotIn('Cc', message)
