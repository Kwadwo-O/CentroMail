"""Combined inbox pagination and source-account routing without live providers."""
import unittest
from unittest.mock import Mock, patch

import app as a
import email_providers
import graph_mail
import test_email_providers as fixtures
from test_accessibility import PageMarkup
from test_integrations import IntegrationFixture


class AllInboxesTests(IntegrationFixture):
    def setUp(self):
        super().setUp()
        with a.app.app_context():
            a.store_google_token(self.user_id, {'access_token':'primary-token', 'expires_at':a.time.time()+3600})
            self.imap = {**fixtures.MailProtocolTests.config, 'name':'IMAP', 'kind':'imap'}
            self.microsoft = {'account_id':'b'*12, 'kind':'microsoft', 'name':'Outlook', 'email':'outlook@example.com',
                              'token':{'access_token':'microsoft-token', 'expires_at':a.time.time()+3600}}
            self.google = {'account_id':'c'*12, 'kind':'gmail', 'name':'Gmail', 'email':'second@example.com',
                           'token':{'access_token':'second-token', 'expires_at':a.time.time()+3600}}
            for key, config in (('email:imap:account', self.imap), ('email:microsoft:account', self.microsoft), ('email:gmail:account', self.google)):
                a.save_integration(self.user_id, key, config)
            self.accounts = a.email_accounts(a.find_user('integrations@example.com'))
        self.login()

    def rows(self, response):
        return [attrs for tag, attrs, _ in PageMarkup(response.json['html']).elements if tag == 'article']

    def message(self, index, account):
        identifier = str(index)
        if account['kind'] == 'gmail': identifier = a.gmail_message_key(account, identifier)
        elif account['kind'] == 'imap': identifier = email_providers.make_id(account['config'], 'inbox', '1', index)
        else: identifier = graph_mail.message_id(account['config'], identifier)
        return {'id':identifier, 'sender':'Sender', 'email':'sender@example.com', 'subject':'Message '+str(index),
                'preview':'Preview', 'internal_date':str(index), 'unread':True, 'starred':False,
                'category':'primary', 'label_ids':['INBOX'], 'date':'Today', 'time':'Now'}

    def test_button_and_composer_preserve_the_selected_real_account(self):
        with self.client.session_transaction() as session: session['mail_account'] = 'email:imap:account'
        response = self.client.get('/inbox?account=all')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-account="all"', response.data)
        self.assertIn(b'All inboxes</span>', response.data)
        self.assertIn(b'<h1 id="inbox-title">All inboxes</h1>', response.data)
        self.assertIn(b'name="account" value="email:imap:account"', response.data)
        self.assertIn(b'data-compose-from>mail@example.com', response.data)
        self.assertNotIn(b'aria-label="Inbox category"', response.data)
        with self.client.session_transaction() as session:
            self.assertEqual(session['mail_account'], 'email:imap:account')
        self.assertEqual(self.client.get('/inbox?account=all&folder=sent').status_code, 404)

    def test_every_account_reaches_all_pages_and_rows_keep_real_reader_links(self):
        sizes = {account['key']: 61 + index for index, account in enumerate(self.accounts)}
        calls = []
        def fetch(user, folder, cursor='', query='', refresh=False, account=None):
            calls.append((account['key'], folder, cursor, query))
            start, total = int(cursor or 0), sizes[account['key']]
            stop = min(start + 25, total)
            return [self.message(index+1, account) for index in range(start, stop)], str(stop) if stop < total else None, total
        loaded, cursor = [], ''
        with patch.object(a, 'fetch_mail_page', side_effect=fetch):
            for _ in range(5):
                response = self.client.get('/api/mail/messages', query_string={'account':'all', 'cursor':cursor})
                self.assertEqual(response.status_code, 200)
                loaded.extend(self.rows(response))
                cursor = response.json['next_cursor']
                if not cursor: break
        self.assertIsNone(cursor)
        self.assertEqual(len(loaded), sum(sizes.values()))
        self.assertEqual(len({(row['data-mail-account'], row['data-message-id']) for row in loaded}), len(loaded))
        for account in self.accounts:
            rows = [row for row in loaded if row['data-mail-account'] == account['key']]
            self.assertEqual(len(rows), sizes[account['key']])
            self.assertTrue(all('account='+account['key'] in row['data-message-url'] and row['data-mail-folder']=='inbox' for row in rows))
            self.assertEqual([call[2] for call in calls if call[0] == account['key']], ['', '25', '50'])

    def test_search_reaches_every_provider_and_cursor_cannot_be_tampered_with(self):
        with patch.object(a, 'fetch_mail_page', return_value=([], 'next', 50)) as fetch:
            response = self.client.get('/api/mail/messages?account=all&search=invoice&category=primary')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(fetch.call_count, len(self.accounts))
            self.assertTrue(all(call.args[3] == 'invoice' for call in fetch.call_args_list))
            cursor = response.json['next_cursor']
            fetch.reset_mock()
            response = self.client.get('/api/mail/messages', query_string={'account':'all', 'search':'invoice', 'cursor':cursor+'tampered'})
            self.assertGreaterEqual(response.status_code, 400)
            fetch.assert_not_called()

    def test_one_unavailable_account_does_not_hide_other_inboxes_or_the_warning(self):
        def fetch(user, folder, cursor='', query='', refresh=False, account=None):
            if account['kind'] == 'imap': raise RuntimeError('Connection unavailable')
            return [self.message(1, account)], 'next' if not cursor else None, 2
        with patch.object(a, 'fetch_mail_page', side_effect=fetch):
            first = self.client.get('/api/mail/messages?account=all')
            second = self.client.get('/api/mail/messages', query_string={'account':'all', 'cursor':first.json['next_cursor']})
        for response in (first, second):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(self.rows(response)), 3)
            self.assertIn('mail@example.com', response.json['warning'])
            self.assertIsNone(response.json['total'])

    def test_primary_and_second_gmail_use_their_own_tokens_and_ids(self):
        result = Mock()
        result.json.return_value = {'messages':[{'id':'shared'}], 'resultSizeEstimate':1}
        metadata = {'id':'shared', 'subject':'Shared', 'sender':'Sender', 'email':'sender@example.com', 'preview':'', 'unread':False, 'starred':False}
        with a.app.test_request_context('/api/mail/messages?account=all'), patch.object(a.google_requests, 'get', return_value=result) as get, patch.object(a, '_fetch_gmail_detail', side_effect=lambda *args:metadata.copy()):
            user = a.find_user('integrations@example.com')
            primary, secondary = [account for account in self.accounts if account['kind'] == 'gmail']
            first, _, _ = a.fetch_mail_page(user, 'inbox', account=primary)
            second, _, _ = a.fetch_mail_page(user, 'inbox', account=secondary)
        self.assertEqual(first[0]['id'], 'shared')
        self.assertEqual(second[0]['id'], 'gm-'+'c'*12+'-shared')
        self.assertEqual([call.kwargs['headers']['Authorization'] for call in get.call_args_list], ['Bearer primary-token', 'Bearer second-token'])

    def test_unread_count_sums_every_connected_provider(self):
        result = Mock()
        result.json.return_value = {'messagesUnread':3, 'messagesTotal':4}
        with patch.object(a.google_requests, 'get', return_value=result), patch.object(graph_mail, 'request', return_value={'unreadItemCount':5}), patch.object(email_providers, 'imap_connect') as imap:
            imap.return_value.__enter__.return_value.status.return_value = ('OK', [b'INBOX (UNSEEN 7)'])
            response = self.client.get('/api/mail/counts?account=all')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'all_inboxes':18})

    def test_aggregate_actions_are_rejected_and_real_actions_do_not_switch_from_account(self):
        with self.client.session_transaction() as session: session['mail_account'] = 'gmail'
        with patch.object(a.google_requests, 'post') as google, patch.object(email_providers, 'change_messages') as imap:
            response = self.post_form('/api/mail/action', {'account':'all', 'action':'read', 'message_ids':'sample'})
            self.assertEqual(response.status_code, 400)
            google.assert_not_called()
            imap.assert_not_called()
            identifier = email_providers.make_id(self.imap, 'inbox', '1', 1)
            response = self.post_form('/api/mail/action', {'account':'email:imap:account', 'folder':'inbox', 'action':'read', 'message_ids':identifier})
            self.assertEqual(response.status_code, 200)
            imap.assert_called_once_with(self.imap, [identifier], 'read', 'inbox')
        with self.client.session_transaction() as session: self.assertEqual(session['mail_account'], 'gmail')


if __name__ == '__main__': unittest.main()
