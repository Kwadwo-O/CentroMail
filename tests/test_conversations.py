"""Email chains, account routing and exact IMAP references without live mail."""
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import app as a
import email_providers
import graph_mail
from test_accessibility import PageMarkup
from test_integrations import IntegrationFixture


class ConversationTests(IntegrationFixture):
    def setUp(self):
        super().setUp()
        self.login()
        with a.app.app_context():
            a.store_google_token(self.user_id, {'access_token': 'fixture-token', 'expires_at': a.time.time() + 3600})

    def payload(self, identifier, timestamp, *, folder='inbox'):
        return {'id': identifier, 'threadId': 'thread-123', 'internalDate': str(timestamp),
            'labelIds': ['SENT'] if folder == 'sent' else ['INBOX', 'UNREAD'],
            'snippet': 'An earlier email in this chain.', 'payload': {'headers': [
                {'name': 'From', 'value': 'Alice <alice@example.com>'},
                {'name': 'To', 'value': 'integrations@example.com'},
                {'name': 'Subject', 'value': 'Project update'},
                {'name': 'Message-ID', 'value': '<' + identifier + '@example.com>'},
            ]}}

    def cache(self, payload):
        with a.app.app_context():
            a.gmail_cache_put(self.user_id, payload['id'],
                metadata=a.gmail_metadata_from_payload(payload, payload['id']), body={'text': 'Selected email body.'})

    def save_account(self, kind):
        config = {'kind': kind, 'name': 'Work email', 'account_id': 'a' * 12, 'email': 'mail@example.com',
            'folders': {'inbox': 'INBOX', 'sent': 'Sent'},
            'token': {'access_token': 'fixture-token', 'expires_at': a.time.time() + 3600}}
        key = 'email:' + kind + ':' + config['account_id']
        with a.app.app_context():
            a.save_integration(self.user_id, key, config)
        return key, config

    def test_gmail_chain_is_ordered_expandable_and_keeps_selected_body_slot(self):
        selected = self.payload('current', 200)
        self.cache(selected)
        response = Mock()
        response.json.return_value = {'messages': [self.payload('latest', 300), selected,
            self.payload('first', 100, folder='sent'), selected]}
        with patch.object(a.google_requests, 'get', return_value=response) as fetch:
            result = self.client.get('/api/mail/conversations/current')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['count'], 3)
        fetch.assert_called_once()
        self.assertIn('/threads/thread-123', fetch.call_args.args[0])
        html = result.json['html']
        self.assertIn('3 emails', html)
        self.assertIn('alice@example.com', html)
        self.assertIn('An earlier email in this chain.', html)
        self.assertLess(html.index('message/first'), html.index('data-current-message'))
        self.assertLess(html.index('data-current-message'), html.index('message/latest'))
        elements = PageMarkup(html).elements
        cards = [attrs for tag, attrs, _ in elements if tag == 'details']
        self.assertEqual(len(cards), 3)
        self.assertIn('open', cards[1])
        self.assertNotIn('data-conversation-message-url', cards[1])
        self.assertEqual(sum('data-current-message' in attrs for _, attrs, _ in elements), 1)
        self.assertIn('data-expand-conversation', html)
        self.assertIn('data-collapse-conversation', html)
        self.assertIn('folder=sent', cards[0]['data-conversation-message-url'])

    def test_single_email_keeps_reader_and_foreign_threads_are_rejected(self):
        selected = self.payload('current', 200)
        self.cache(selected)
        response = Mock()
        response.json.return_value = {'messages': [selected]}
        with patch.object(a.google_requests, 'get', return_value=response):
            result = self.client.get('/api/mail/conversations/current')
        self.assertEqual(result.json, {'html': '', 'count': 1})
        response.json.return_value = {'messages': [{**selected, 'threadId': 'another-thread'}]}
        with patch.object(a.google_requests, 'get', return_value=response):
            self.assertEqual(self.client.get('/api/mail/conversations/current').status_code, 502)
        with patch.object(a.google_requests, 'get') as fetch:
            self.assertEqual(self.client.get('/api/mail/conversations/gm-foreign-current').status_code, 400)
        fetch.assert_not_called()

    def test_imap_and_microsoft_chain_links_keep_account_and_folder(self):
        for kind in ('imap', 'microsoft'):
            with self.subTest(kind=kind):
                key, config = self.save_account(kind)
                identifier = email_providers.make_id(config, 'inbox', '123', 7) if kind == 'imap' else graph_mail.message_id(config, 'current')
                earlier_id = email_providers.make_id(config, 'sent', '456', 4) if kind == 'imap' else graph_mail.message_id(config, 'first')
                selected = {**self.payload(identifier, 200), 'mail_folder': 'inbox'}
                earlier = {**self.payload(earlier_id, 100, folder='sent'), 'mail_folder': 'sent'}
                self.cache(selected)
                provider = email_providers if kind == 'imap' else graph_mail
                with patch.object(provider, 'conversation_messages', return_value=[earlier, selected]) as fetch:
                    result = self.client.get('/api/mail/conversations/' + identifier, query_string={'account': key})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json['count'], 2)
                cards = [attrs for tag, attrs, _ in PageMarkup(result.json['html']).elements if tag == 'details']
                query = parse_qs(urlparse(cards[0]['data-conversation-message-url']).query)
                self.assertEqual(query['account'], [key])
                self.assertEqual(query['folder'], ['sent'])
                fetch.assert_called_once()
                if kind == 'imap':
                    self.assertEqual(fetch.call_args.args[2], 'inbox')
                else:
                    self.assertEqual(fetch.call_args.args[0], 'fixture-token')


class ImapConversationTests(unittest.TestCase):
    config = {'account_id': 'a' * 12, 'folders': {'inbox': 'INBOX', 'sent': 'Sent'}}

    def test_search_hits_require_exact_thread_reference_and_duplicates_are_removed(self):
        current_id = email_providers.make_id(self.config, 'inbox', '123', 7)
        current = {'id': current_id, 'message_id': '<current@example.com>', 'references': '<root@example.com>'}
        good = b'From: Alice <alice@example.com>\r\nMessage-ID: <reply@example.com>\r\nReferences: <root@example.com>\r\n\r\n'
        unrelated = b'Message-ID: <other@example.com>\r\nReferences: <root@example.com.invalid>\r\n\r\n'
        with patch.object(email_providers, 'imap_connect') as connect:
            client = connect.return_value.__enter__.return_value
            client.select.return_value = ('OK', [])
            client.response.return_value = ('UIDVALIDITY', [b'123'])
            client.uid.side_effect = lambda command, *args: ('OK', [b'7 8']) if command == 'SEARCH' else (
                'OK', [(b'1 (UID 7 FLAGS (\\Seen))', good), (b'2 (UID 8 FLAGS ())', unrelated)])
            messages = email_providers.conversation_messages(self.config, current, 'inbox')
        self.assertEqual(len(messages), 1)
        searches = [call for call in client.uid.call_args_list if call.args[0] == 'SEARCH']
        self.assertEqual(len(searches), 2)
        self.assertIn(b'"<root@example.com>"', searches[0].args)

    def test_non_ascii_received_ids_cannot_crash_ascii_imap_search(self):
        with patch.object(email_providers, 'imap_connect') as connect:
            self.assertEqual(email_providers.conversation_messages(self.config,
                {'message_id': '<café@example.com>', 'references': '<original@例子.com>'}, 'inbox'), [])
        connect.assert_not_called()
