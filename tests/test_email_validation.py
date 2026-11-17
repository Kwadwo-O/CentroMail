"""DNS validation and spam tags without contacting real mailboxes."""
import unittest
from unittest.mock import Mock, patch

import dns.exception
import dns.resolver
import email_validation as validation
import app as a
import test_auth
from test_integrations import IntegrationFixture


class AddressValidationTests(unittest.TestCase):
    def test_syntax_checks_reject_header_injection_and_do_not_query_dns(self):
        with patch.object(validation.resolver, 'resolve') as resolve:
            for address in ('bad..name@gmail.com', 'person@bad..domain.com', 'person@gmail.com\r\nBcc:other@gmail.com', 'person@-domain.com', 'a' * 65 + '@gmail.com'):
                self.assertTrue(validation.email_address_error(address), address)
            self.assertEqual(validation.email_address_error('person+tag@gmail.com'), '')
        resolve.assert_not_called()

    def test_mail_records_and_public_address_fallback_are_accepted(self):
        with patch.object(validation.resolver, 'resolve', return_value=[Mock(preference=10, exchange='mx.domain.com.')]):
            self.assertEqual(validation.email_address_error('person@domain.com', check_domain=True), '')
        with patch.object(validation.resolver, 'resolve', side_effect=[dns.resolver.NoAnswer(), [Mock(address='8.8.8.8')], dns.resolver.NoAnswer()]):
            self.assertEqual(validation.email_address_error('person@domain.com', check_domain=True), '')

    def test_missing_domains_null_mx_and_unavailable_dns_have_distinct_errors(self):
        for answer in (dns.resolver.NXDOMAIN(), [Mock(preference=0, exchange='.')]):
            with patch.object(validation.resolver, 'resolve', side_effect=answer if isinstance(answer, Exception) else None, return_value=answer):
                self.assertIn('cannot receive email', validation.email_address_error('person@domain.com', check_domain=True))
        for failure in (dns.exception.Timeout(), dns.resolver.NoNameservers()):
            with patch.object(validation.resolver, 'resolve', side_effect=failure):
                self.assertIn('could not be checked right now', validation.email_address_error('person@domain.com', check_domain=True))


class AddressValidationRoutes(unittest.TestCase):
    def setUp(self):
        self.auth = test_auth.AuthTests()
        self.auth.setUp()
        self.addCleanup(self.auth.doCleanups)

    def test_invalid_auth_email_is_shown_inline_without_creating_an_account(self):
        for route in ('/login', '/register'):
            with self.subTest(route=route):
                with patch.object(validation.resolver, 'resolve') as resolve:
                    response = self.auth.post(route, {
                        'email':'bad..name@gmail.com', 'name':'Test Person',
                        'password':self.auth.password, 'confirm_password':self.auth.password,
                    })
                resolve.assert_not_called()
                self.assertIn(b'aria-invalid="true"', response.data)
                error_id = b'signupEmailError' if route == '/register' else b'loginEmailError'
                self.assertIn(b'aria-describedby="' + error_id + b'"', response.data)
                self.assertIn(b'Please enter a valid email address.', response.data)
                self.assertIn(b'bad..name@gmail.com', response.data)
                self.assertEqual(self.auth.users(), [])

    def test_registration_rejects_undeliverable_address_without_creating_account(self):
        with patch.object(validation.resolver, 'resolve', side_effect=dns.resolver.NXDOMAIN()):
            response = self.auth.register(email='person@missing-domain.com')
        self.assertIn(b'cannot receive email', response.data)
        self.assertIn(b'aria-invalid="true"', response.data)
        self.assertIn(b'aria-describedby="signupEmailError"', response.data)
        self.assertEqual(self.auth.users(), [])
        self.assertIn(b'person@missing-domain.com', response.data)

    def test_compose_keeps_draft_and_does_not_send_when_validation_fails(self):
        self.auth.register()
        cases = (('bad..name@gmail.com', None),
                 ('person@domain.com', dns.resolver.NXDOMAIN()),
                 ('person@domain.com', dns.exception.Timeout()))
        for recipient, failure in cases:
            with patch.object(validation.resolver, 'resolve', side_effect=failure), patch.object(a, 'send_gmail_message') as send:
                response = self.auth.post('/compose', {'to':recipient, 'subject':'Keep subject', 'body':'Keep draft'})
            send.assert_not_called()
            self.assertIn(b'aria-invalid="true"', response.data)
            self.assertIn(b'aria-describedby="composeRecipientError"', response.data)
            self.assertIn(b'data-compose-draft', response.data)
            self.assertIn(b'Keep draft', response.data)

    def test_other_compose_errors_do_not_mark_recipient_invalid(self):
        self.auth.register()
        with patch.object(a, 'send_gmail_message') as send:
            response = self.auth.post('/compose', {'to':'person@example.com', 'subject':'Invalid\nsubject', 'body':'Keep draft'})
        send.assert_not_called()
        self.assertIn(b'The email subject must be a single line.', response.data)
        self.assertNotIn(b'aria-invalid="true"', response.data)


class EmailConnectionValidationTests(IntegrationFixture):
    def test_invalid_email_is_shown_inline_without_connecting_or_storing_credentials(self):
        with patch.object(a.email_providers, 'imap_connect') as imap, patch.object(a.email_providers, 'smtp_connect') as smtp:
            response = self.post_form('/integrations/email/connect', {
                'provider':'fastmail', 'email':'bad..name@gmail.com', 'password':'private-app-password',
            })
        imap.assert_not_called()
        smtp.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'aria-invalid="true"', response.data)
        self.assertIn(b'aria-describedby="email-connect-address-error"', response.data)
        self.assertIn(b'Enter a valid email address.', response.data)
        self.assertIn(b'bad..name@gmail.com', response.data)
        self.assertNotIn(b'private-app-password', response.data)
        with a.app.app_context():
            self.assertEqual(a.email_accounts(a.find_user('integrations@example.com')), [])


class SpamTagTests(IntegrationFixture):
    def test_spam_tags_show_in_lists_and_both_readers_without_tagging_inbox(self):
        self.login()
        with a.app.app_context():
            a.store_google_token(self.user_id, {'access_token':'fixture', 'expires_at':a.time.time()+3600})
            for identifier, labels in (('spam-message', ['SPAM']), ('inbox-message', ['INBOX'])):
                metadata = a.gmail_metadata_from_payload({'id':identifier, 'labelIds':labels,
                    'payload':{'headers':[{'name':'From','value':'Sender <sender@example.com>'}]}}, identifier)
                a.gmail_cache_put(self.user_id, identifier, metadata=metadata, body={'text':'Message content'})
        for route in ('/inbox?folder=spam', '/message/spam-message?folder=spam', '/message/spam-message?folder=spam&pane=1'):
            self.assertIn(b'class="message-spam m3e-badge m3e-badge--large">Spam</span>', self.client.get(route).data)
        self.assertNotIn(b'class="message-spam', self.client.get('/inbox').data)
        with patch.object(a, 'fetch_mail_page', return_value=([{'id':'cached', 'sender':'Sender', 'email':'sender@example.com', 'subject':'Cached message', 'preview':'', 'time':'', 'category':'primary'}], None, 1)):
            self.assertIn('>Spam</span>', self.client.get('/api/mail/messages?folder=spam').json['html'])
