"""Sender identity, domain boundaries, and offline logo selection."""

import unittest

from sender_logos import sender_logo_source


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


if __name__ == '__main__':
    unittest.main()
