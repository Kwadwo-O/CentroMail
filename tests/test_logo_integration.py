"""Rendered sender logos using disposable accounts and fixture API keys."""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import app as application
from test_accessibility import PageMarkup
from test_integrations import IntegrationFixture


class LogoIntegrationTests(IntegrationFixture):
    public_key = 'pk_fixture_public_only'
    secret_key = 'sk_fixture_never_render_this'

    def setUp(self):
        super().setUp()
        self.login()
        self.enterContext(patch.dict(application.app.config, {
            'CDN_PUBLIC_KEY': self.public_key,
            'LOGO_API_SECRET_KEY': self.secret_key,
        }))

    def message(self, email='private.person@E.LINKEDIN.COM'):
        return dict(id='logo-fixture', sender='Private Person', email=email,
                    subject='Logo fixture', preview='A local fixture message.',
                    time='Nov 16', date='16 November 2026', internal_date=1,
                    category='primary', unread=False, starred=False,
                    can_reply=True, is_no_reply=False, otp_code=None,
                    body={'text': 'A local fixture message.'})

    def rows(self, email='private.person@E.LINKEDIN.COM'):
        with application.app.test_request_context('/inbox'):
            return application.render_template('mail_rows.html', messages=[self.message(email)],
                                               folder='inbox', mail_account_key='gmail')

    def logos(self, html):
        return [attrs for tag, attrs, _ in PageMarkup(html).elements
                if tag == 'img' and 'sender-logo' in attrs.get('class', '').split()]

    def check_cdn_logo(self, html):
        self.assertNotIn(self.secret_key, html)
        self.assertEqual(len(self.logos(html)), 1)
        image = self.logos(html)[0]
        source = urlparse(image['src'])
        self.assertEqual((source.scheme, source.netloc, source.path),
                         ('https', 'img.logo.dev', '/e.linkedin.com'))
        self.assertEqual(parse_qs(source.query), {
            'token': [self.public_key], 'size': ['80'], 'format': ['png'], 'fallback': ['404'],
        })
        self.assertNotIn('private.person', image['src'])
        self.assertNotIn('@', image['src'])
        self.assertEqual(image['data-logo-fallback'], '/static/images/senders/linkedin.png')
        self.assertEqual(image['referrerpolicy'], 'origin')
        self.assertEqual(image['alt'], '')

    def test_rows_render_normalized_cdn_logo_with_local_fallback(self):
        self.check_cdn_logo(self.rows())

    def test_reading_pane_and_full_page_use_the_same_logo(self):
        with patch.object(application, 'fetch_email_message', return_value=self.message()):
            for suffix in ('?pane=1', ''):
                with self.subTest(suffix=suffix):
                    response = self.client.get('/message/logo-fixture' + suffix)
                    self.assertEqual(response.status_code, 200)
                    self.check_cdn_logo(response.text)

    def test_unknown_public_organization_uses_cdn_without_local_fallback(self):
        image = self.logos(self.rows('private.person@MAIL.ACME.CO.UK'))[0]
        self.assertEqual(urlparse(image['src']).path, '/mail.acme.co.uk')
        self.assertNotIn('data-logo-fallback', image)
        self.assertNotIn('private.person', image['src'])

    def test_missing_public_key_retains_local_logo_and_unknown_initials(self):
        application.app.config['CDN_PUBLIC_KEY'] = None
        image = self.logos(self.rows())[0]
        self.assertEqual(image['src'], '/static/images/senders/linkedin.png')
        self.assertNotIn('data-logo-fallback', image)
        self.assertEqual(self.logos(self.rows('person@acme.co.uk')), [])

    def test_secret_key_is_not_accepted_as_a_cdn_public_key(self):
        application.app.config['CDN_PUBLIC_KEY'] = self.secret_key
        html = self.rows()
        self.assertNotIn(self.secret_key, html)
        self.assertEqual(self.logos(html)[0]['src'], '/static/images/senders/linkedin.png')

    def test_personal_reserved_and_malformed_senders_keep_initials(self):
        for email in ('person@gmail.com', 'person@outlook.com', 'person@example.com',
                      'person@service.internal', 'person@127.0.0.1',
                      'person@company.com/path', 'missing-address', ''):
            with self.subTest(email=email):
                self.assertEqual(self.logos(self.rows(email)), [])
