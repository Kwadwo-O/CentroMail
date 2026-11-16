"""Sender identity, domain boundaries, and offline logo selection."""

import unittest
from urllib.parse import parse_qs, urlparse

from sender_logos import logo_cdn_enabled, sender_logo_domain, sender_logo_source


class SenderLogoTests(unittest.TestCase):
    def test_known_brand_uses_local_logo_for_root_and_subdomains(self):
        for value in ('updates@linkedin.com', 'LinkedIn <jobs@e.linkedin.com>',
                      'LinkedIn <jobs@MAIL.LINKEDIN.COM>', 'jobs@linkedin.com.'):
            with self.subTest(value=value):
                self.assertEqual(sender_logo_source(value), 'images/senders/linkedin.png')

    def test_existing_brand_assets_are_selected_without_network_access(self):
        expected = {
            'marketplace-messages@amazon.co.uk': 'images/senders/amazon.ico',
            'notify@github.com': 'images/senders/github.png',
            'updates@studysmarter.de': 'images/senders/studysmarter.svg',
            'notify@facebook.com': 'images/integrations/facebook.svg',
            'notify@twitter.com': 'images/integrations/x.svg',
            'notify@bsky.app': 'images/integrations/bluesky.svg',
            'notify@slack.com': 'images/integrations/slack.svg',
            'notify@accounts.google.com': 'images/Google_Favicon_2025.svg.webp',
            'notify@account.microsoft.com': 'images/Microsoft_Favicon_2025.webp',
        }
        for value, logo in expected.items():
            with self.subTest(value=value):
                self.assertEqual(sender_logo_source(value), logo)

    def test_display_name_and_lookalike_domains_never_select_a_brand(self):
        for value in ('LinkedIn <jobs@notlinkedin.com>',
                      'LinkedIn <jobs@linkedin.com.attacker.com>',
                      'Google <person@unrelated-company.com>'):
            with self.subTest(value=value):
                self.assertIsNone(sender_logo_source(value))
        self.assertIsNone(sender_logo_source('LinkedIn <person@gmail.com>'))

    def test_unknown_organization_keeps_initials(self):
        value = 'Private Person <private.name+mail@MAIL.ACME.CO.UK>'
        self.assertIsNone(sender_logo_source(value))

    def test_unknown_international_domain_keeps_initials(self):
        self.assertIsNone(sender_logo_source('Updates <news@bücher.de>'))

    def test_personal_mailboxes_keep_initials(self):
        for domain in ('gmail.com', 'googlemail.com', 'outlook.com', 'hotmail.co.uk',
                       'live.com', 'yahoo.com', 'yahoo.co.uk', 'icloud.com', 'aol.com',
                       'proton.me', 'pm.me', 'gmx.de', 'mail.com', 'fastmail.com'):
            with self.subTest(domain=domain):
                self.assertIsNone(sender_logo_source(f'person@{domain}'))

    def test_reserved_and_private_domains_keep_initials(self):
        for domain in ('example.com', 'mail.example.org', 'linkedin.com.evil.example',
                       'service.test', 'service.invalid', 'localhost', 'mail.localhost',
                       'mail.local', 'mail.internal', 'mail.lan', 'mail.home.arpa',
                       'mail.corp', 'hidden.onion', 'private.intranet'):
            with self.subTest(domain=domain):
                self.assertIsNone(sender_logo_source(f'user@{domain}'))

    def test_missing_malformed_and_nondns_addresses_keep_initials(self):
        values = (None, 123, {}, '', 'LinkedIn', 'user', 'user@', '@company.com',
                  'user@@company.com', 'user@singlelabel', 'user@-bad.com',
                  'user@bad-.com', 'user@bad_domain.com', 'user@bad..com', 'user@linkedin.com..',
                  'user@company.123', 'user@127.0.0.1', 'user@[127.0.0.1]',
                  'user@[IPv6:::1]', 'user@company.com/path', 'user@company.com:443',
                  'user@company.com?name=test', 'user@company.com\r\nInjected: yes',
                  'user@' + 'a' * 64 + '.com', 'user@' + '.'.join(['a' * 63] * 5) + '.com')
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(sender_logo_source(value))

    def test_domain_extraction_normalizes_case_fqdn_and_international_names(self):
        self.assertEqual(sender_logo_domain('Updates <news@MAIL.ACME.CO.UK.>'), 'mail.acme.co.uk')
        self.assertEqual(sender_logo_domain('Updates <news@bücher.de>'), 'xn--bcher-kva.de')

    def test_cdn_uses_only_organization_domain_and_publishable_key(self):
        key = 'pk_fixture_public-key_123'
        value = 'Private Person <private.name+mail@MAIL.ACME.CO.UK>'
        source = sender_logo_source(value, key)
        url = urlparse(source)
        self.assertEqual((url.scheme, url.netloc, url.path), ('https', 'img.logo.dev', '/mail.acme.co.uk'))
        self.assertEqual(parse_qs(url.query), {'token': [key], 'size': ['80'], 'format': ['png'], 'fallback': ['404']})
        self.assertNotIn('Private', source)
        self.assertNotIn('private.name', source)
        self.assertNotIn('@', source)

    def test_configured_cdn_supports_known_brands_and_idna_domains(self):
        for address, domain in (
            ('LinkedIn <jobs@e.linkedin.com>', 'e.linkedin.com'),
            ('Updates <news@bücher.de>', 'xn--bcher-kva.de'),
        ):
            with self.subTest(address=address):
                self.assertEqual(urlparse(sender_logo_source(address, 'pk_fixture')).path, '/' + domain)

    def test_cdn_excludes_personal_nonpublic_and_unsafe_domains(self):
        for value in ('LinkedIn <person@gmail.com>', 'user@outlook.com', 'user@example.com',
                      'user@service.test', 'user@internal.lan', 'user@127.0.0.1',
                      'user@[IPv6:::1]', 'user@company.com/path', 'user@company.com?token=x',
                      'user@company.com\r\nInjected: yes', None):
            with self.subTest(value=value):
                self.assertIsNone(sender_logo_source(value, 'pk_fixture'))

    def test_invalid_and_secret_keys_preserve_local_fallbacks(self):
        for key in (None, '', 123, {}, 'sk_fixture_secret', 'PK_fixture', 'pk_',
                    ' pk_fixture', 'pk_fixture ', 'pk_fixture\n', 'pk_value&other=1'):
            with self.subTest(key=key):
                self.assertFalse(logo_cdn_enabled(key))
                self.assertEqual(sender_logo_source('jobs@linkedin.com', key), 'images/senders/linkedin.png')
                self.assertIsNone(sender_logo_source('person@acme.co.uk', key))
        self.assertTrue(logo_cdn_enabled('pk_fixture_public-key_123'))


if __name__ == '__main__':
    unittest.main()
