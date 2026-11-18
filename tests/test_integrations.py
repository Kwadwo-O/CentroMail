"""Integration page and webhook tests using a disposable SQLite database."""

import json
import hashlib
import hmac
import ssl
from unittest.mock import AsyncMock, Mock, patch
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

import app as application


class IntegrationFixture(unittest.TestCase):
    def setUp(self):
        dns = patch('email_validation.resolver')
        self.addCleanup(dns.stop)
        dns.start().resolve.return_value = [Mock(preference=10, exchange='mx.example.com.')]
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.previous_config = {
            key: application.app.config.get(key)
            for key in ("DATABASE", "TESTING", "SECRET_KEY", "WHATSAPP_APP_SECRET")
        }
        self.addCleanup(application.app.config.update, self.previous_config)
        application.app.config.update(
            DATABASE=str(Path(self.directory.name) / "test.sqlite"),
            TESTING=True,
            SECRET_KEY="test-only-secret",
            WHATSAPP_APP_SECRET="test-meta-secret",
        )
        with application.app.app_context():
            application.init_db()
            db = application.get_db()
            db.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                ("Integration Tester", "integrations@example.com", generate_password_hash("x" * 16)),
            )
            db.commit()
            self.user_id = db.execute(
                "SELECT id FROM users WHERE email = ?", ("integrations@example.com",)
            ).fetchone()["id"]
        self.client = application.app.test_client()


    def login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id
            session["user_email"] = "integrations@example.com"
            session["csrf_token"] = "test-token"


    def post_form(self, path, data):
        self.login()
        return self.client.post(
            path,
            data={"csrf_token": "test-token", **data},
            follow_redirects=True,
        )


    def save_whatsapp(self, verify_token="verify_me_123"):
        with application.app.app_context():
            db = application.get_db()
            db.execute(
                """INSERT INTO integrations (user_id, provider, config, updated_at)
                   VALUES (?, 'whatsapp', ?, ?)
                   ON CONFLICT(user_id, provider) DO UPDATE SET config = excluded.config""",
                (
                    self.user_id,
                    json.dumps(
                        {
                            "phone_number_id": "123456789012345",
                            "access_token": "EAABtest",
                            "verify_token": verify_token,
                            "verified_name": "Test Business",
                            "display_phone_number": "+1 555 0100",
                        }
                    ),
                    application.time.time(),
                ),
            )
            db.commit()


    def signed_webhook(self, path, *, json):
        body = application.app.json.dumps(json).encode()
        signature = "sha256=" + hmac.new(b"test-meta-secret", body, hashlib.sha256).hexdigest()
        return self.client.post(path, data=body, content_type="application/json", headers={"X-Hub-Signature-256": signature})


class IntegrationTests(IntegrationFixture):
    def test_catalog_guides_setup_without_exposing_credentials(self):
        self.login()
        with patch.dict(application.app.config, {'GOOGLE_CLIENT_ID': 'private-client',
                'GOOGLE_CLIENT_SECRET': 'private-secret', 'MICROSOFT_CLIENT_ID': None,
                'MICROSOFT_CLIENT_SECRET': None}):
            body = self.client.get('/integrations').text
        self.assertIn('Search apps', body)
        self.assertIn('Coming soon', body)
        self.assertNotIn('Manual OAuth token', body)
        self.assertIn('Setup required', body)
        self.assertIn('/static/images/integrations/outlook.svg', body)
        self.assertNotIn('private-secret', body)
        self.assertNotIn('private-client', body)
        self.assertNotIn('browser-storage-card', body)
        for item in application.integration_catalog.APPS:
            if item['key'] in application.integration_catalog.PLACEHOLDER_PROVIDERS:
                self.assertNotIn('id="integration-dialog-' + item['key'] + '"', body)
            else:
                self.assertIn('id="integration-dialog-' + item['key'] + '"', body)
            self.assertTrue((Path(application.app.root_path) / 'static/images/integrations' / (item['key'] + '.svg')).is_file())

    def test_deferred_oauth_apps_are_placeholders_and_cannot_contact_providers(self):
        from test_accessibility import PageMarkup
        self.login()
        deferred = {'x', 'linkedin', 'reddit', 'tiktok', 'pinterest', 'tumblr', 'twitch'}
        self.assertEqual(application.integration_catalog.PLACEHOLDER_PROVIDERS, deferred)
        with application.app.app_context():
            for provider in deferred:
                application.save_integration(self.user_id, 'social:' + provider,
                    {'access_token':'private-saved-token', 'account':'Previously connected'})
        with patch.object(application, 'social_profile') as profile, patch.object(application, 'social_publish') as publish:
            body = self.client.get('/integrations?app=x').text
            elements = PageMarkup(body).elements
            cards = {attrs['data-integration-app']: attrs for tag, attrs, _ in elements if 'data-integration-app' in attrs}
            buttons = {attrs.get('aria-label'): attrs for tag, attrs, _ in elements if tag == 'button'}
            self.assertIn('0 apps connected', body)
            self.assertIn('data-open-integration=""', body)
            self.assertNotIn('private-saved-token', body)
            self.assertNotIn('Previously connected', body)
            for provider in deferred:
                name = application.integration_catalog.APPS_BY_KEY[provider]['name']
                self.assertEqual(cards[provider]['data-connected'], 'false')
                self.assertIn('disabled', buttons[name + ' — coming soon'])
                self.assertNotIn('/integrations/social/' + provider, body)
                for path in (f'/integrations/social/{provider}/connect', f'/integrations/social/{provider}/test',
                             f'/api/integrations/{provider}/check'):
                    result = self.client.post(path, data={'csrf_token':'test-token', 'access_token':'unused', 'message':'unused'})
                    self.assertEqual(result.status_code, 409)
                    self.assertIn('coming soon', result.text)
            profile.assert_not_called(); publish.assert_not_called()
        with application.app.test_request_context('/inbox'):
            self.assertFalse({item['key'] for item in application.workspace_connections({'id':self.user_id})} & deferred)
        with application.app.app_context():
            for provider in deferred:
                self.assertIsNotNone(application.get_integration(self.user_id, 'social:' + provider))

    def test_telegram_pending_and_validation_reopen_the_right_dialog(self):
        self.login()
        with application.app.app_context():
            application.save_integration(self.user_id, 'telegram', {'stage':'password', 'phone':'+15550100'})
        body = self.client.get('/integrations').text
        self.assertIn('data-open-integration="telegram"', body)
        self.assertIn('/integrations/telegram/password', body)
        response = self.client.post('/integrations/discord', data={'csrf_token':'test-token', 'bot_token':'bad'})
        self.assertIn('app=discord', response.location)
        self.assertIn('valid Discord bot token', self.client.get(response.location).text)

    def test_connection_check_requires_login_csrf_and_saved_connection(self):
        path = '/api/integrations/discord/check'
        self.assertEqual(self.client.post(path).status_code, 302)
        self.login()
        self.assertEqual(self.client.post(path).status_code, 400)
        result = self.client.post(path, data={'csrf_token':'test-token'})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.post('/api/integrations/facebook/check', data={'csrf_token':'test-token'}).status_code, 404)

    def test_connection_checks_do_not_send_or_publish(self):
        self.login()
        with application.app.app_context():
            application.save_integration(self.user_id, 'discord', {'channel_id':'123', 'bot_token':'private-token'})
            application.save_integration(self.user_id, 'whatsapp', {'phone_number_id':'123', 'access_token':'private-token'})
            application.save_integration(self.user_id, 'social:mastodon', {'access_token':'private-token'})
            application.save_integration(self.user_id, 'social:bluesky', {'access_token':'private-token'})
        with patch.object(application, 'discord_request', return_value={}) as discord, \
             patch.object(application, 'whatsapp_request', return_value={}) as whatsapp, \
             patch.object(application, 'social_profile', return_value={}) as social, \
             patch.object(application, 'social_request', return_value={}) as bluesky, \
             patch.object(application, 'discord_send_message') as send, \
             patch.object(application, 'social_publish') as publish:
            for provider in ('discord', 'whatsapp', 'mastodon', 'bluesky'):
                result = self.client.post('/api/integrations/' + provider + '/check', data={'csrf_token':'test-token'})
                self.assertEqual(result.status_code, 200)
                self.assertNotIn('private-token', result.text)
            self.assertTrue(all(call.args[1] == 'GET' for call in discord.call_args_list))
            self.assertEqual(whatsapp.call_args.args[1], 'GET')
            self.assertEqual(social.call_args.args[0], 'mastodon')
            self.assertIn('getSession', bluesky.call_args.args[0])
            send.assert_not_called(); publish.assert_not_called()

    def test_telegram_check_releases_client_and_never_sends(self):
        self.login()
        with application.app.app_context():
            application.save_integration(self.user_id, 'telegram', {'stage':'connected'})
        client = Mock(connect=AsyncMock(), disconnect=AsyncMock(),
                      is_user_authorized=AsyncMock(return_value=True), get_me=AsyncMock())
        with patch.object(application, '_telegram_client', return_value=client), patch.object(application, 'telegram_send_test') as send:
            response = self.client.post('/api/integrations/telegram/check', data={'csrf_token':'test-token'})
            self.assertEqual(response.status_code, 200)
            client.disconnect.assert_awaited_once()
            send.assert_not_called()
            client.is_user_authorized.return_value = False
            response = self.client.post('/api/integrations/telegram/check', data={'csrf_token':'test-token'})
            self.assertEqual(response.status_code, 502)
            self.assertIn('session expired', response.json['error'])

    def test_tiktok_check_uses_only_basic_profile_fields(self):
        with patch.object(application, 'social_request', return_value={'data':{'user':{'open_id':'test-id', 'display_name':'Tester'}}}) as call:
            application.social_profile('tiktok', {'access_token':'fixture'})
        self.assertEqual(call.call_args.kwargs['params']['fields'], 'open_id,display_name')
        with patch.object(application, 'social_request', return_value={'error':{'code':'access_token_invalid'}}), self.assertRaises(RuntimeError):
            application.social_profile('tiktok', {'access_token':'fixture'})

    def test_manual_connection_rejects_oversize_credentials_without_network(self):
        with patch.object(application, 'social_profile') as profile, self.assertRaises(RuntimeError):
            application.social_connect('x', {'access_token':'x' * 4097})
        profile.assert_not_called()

    def test_whatsapp_malformed_signature_is_rejected_without_server_error(self):
        response=self.client.post('/integrations/whatsapp/webhook',json={},headers={'X-Hub-Signature-256':'sha256=é'})
        self.assertEqual(response.status_code,403)


    def test_integrations_page_renders_every_card(self):
        self.login()
        response = self.client.get("/integrations")
        self.assertEqual(response.status_code, 200)
        body = response.data
        for label in (b"Gmail", b"Telegram", b"WhatsApp", b"Discord"):
            self.assertIn(label, body)
        self.assertIn(b"/integrations/telegram/start", body)
        self.assertIn(b"/integrations/whatsapp", body)
        self.assertIn(b"/integrations/discord", body)

    def test_integrations_require_login(self):
        response = self.client.get("/integrations")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_removed_social_services_are_hidden_and_reject_saved_connections(self):
        self.login()
        removed = ('facebook', 'instagram', 'snapchat', 'threads')
        with application.app.app_context():
            for provider in removed:
                application.save_integration(self.user_id, 'social:' + provider,
                    {'access_token': 'old-token', 'account': 'Old account'})
        with patch.object(application, 'social_request', side_effect=AssertionError('Removed services must not contact providers')):
            body = self.client.get('/integrations').text
            for provider in removed:
                with self.subTest(provider=provider):
                    self.assertNotIn('/integrations/social/' + provider, body)
                    self.assertNotIn('"key": "' + provider + '"', body)
                    for action in ('connect', 'test', 'disconnect'):
                        response = self.client.post(f'/integrations/social/{provider}/{action}',
                            data={'csrf_token': 'test-token', 'access_token': 'old-token', 'message': 'Hello'})
                        self.assertEqual(response.status_code, 404)
            with application.app.test_request_context('/inbox'):
                connections = application.workspace_connections({'id': self.user_id})
            self.assertFalse({item['key'] for item in connections} & set(removed))
        self.assertIn('/integrations/social/mastodon/connect', body)
        self.assertIn('/integrations/whatsapp', body)

    def test_whatsapp_webhook_verification(self):
        self.save_whatsapp()
        response = self.client.get(
            "/integrations/whatsapp/webhook",
            query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify_me_123",
                "hub.challenge": "challenge-accepted",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"challenge-accepted")

    def test_whatsapp_webhook_rejects_bad_token(self):
        self.save_whatsapp()
        response = self.client.get(
            "/integrations/whatsapp/webhook",
            query_string={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "nope",
            },
        )
        self.assertEqual(response.status_code, 403)


    def test_unsigned_or_invalid_webhooks_cannot_store_messages(self):
        self.save_whatsapp()
        for headers in ({}, {"X-Hub-Signature-256": "sha256=" + "0" * 64}):
            response = self.client.post("/integrations/whatsapp/webhook", json={"entry": []}, headers=headers)
            self.assertEqual(response.status_code, 403)
        with application.app.app_context():
            self.assertEqual(application.whatsapp_recent_messages(self.user_id), [])

    def test_webhook_requires_configured_app_secret(self):
        application.app.config["WHATSAPP_APP_SECRET"] = None
        self.assertEqual(self.client.post("/integrations/whatsapp/webhook", json={}).status_code, 503)

    def test_connections_render_without_waiting_for_live_messages(self):
        self.login()
        with application.app.app_context():
            application.save_integration(self.user_id, "telegram", {"stage": "connected", "account": {"name": "Example"}})
            application.save_integration(self.user_id, "discord", {"channel_id": "123"})
        with patch.object(application, "telegram_snapshot") as telegram, patch.object(application, "discord_recent_messages") as discord:
            response = self.client.get("/integrations")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(b'data-integration-feed', response.data)
            self.assertIn(b'Check connection', response.data)
            telegram.assert_not_called(); discord.assert_not_called()
        with patch.object(application, "discord_recent_messages", return_value=[{"sender":"Example", "text":"Hello", "time":"Now"}]):
            response = self.client.get("/api/integrations/discord/messages")
            self.assertEqual(response.json["messages"][0]["text"], "Hello")
        with patch.object(application, "discord_recent_messages", side_effect=RuntimeError("unavailable")):
            self.assertEqual(self.client.get("/api/integrations/discord/messages").status_code, 502)
        self.assertEqual(application.app.test_client().get("/api/integrations/discord/messages").status_code, 302)

    def test_mastodon_rejects_private_destinations_and_unsafe_urls(self):
        for instance in ("example.com@127.0.0.1", "http://mastodon.social", "mastodon.social/private", "mastodon.social:5443"):
            with self.subTest(instance=instance), self.assertRaises(RuntimeError):
                application.mastodon_base_url(instance)
        for address in ("127.0.0.1", "192.168.1.1", "::1", "169.254.169.254"):
            with patch.object(application.socket, "getaddrinfo", return_value=[(2,1,6,"",(address,443))]), self.assertRaises(RuntimeError):
                application.mastodon_request("https://mastodon.social", "/api/v1/accounts/verify_credentials", "test")

    def test_mastodon_pins_public_dns_and_checks_tls_without_redirects(self):
        with patch.object(application.socket, "getaddrinfo", return_value=[(2,1,6,"",("8.8.8.8",443))]), patch.object(application.urllib3, "HTTPSConnectionPool") as factory:
            pool = factory.return_value.__enter__.return_value
            pool.urlopen.return_value = Mock(status=200, data=b'{"acct":"example"}')
            result = application.mastodon_request("https://mastodon.social", "/api/v1/accounts/verify_credentials", "test")
            self.assertEqual(result["acct"], "example")
            self.assertEqual(factory.call_args.args, ("8.8.8.8",))
            self.assertEqual(factory.call_args.kwargs["assert_hostname"], "mastodon.social")
            self.assertEqual(factory.call_args.kwargs["server_hostname"], "mastodon.social")
            self.assertEqual(factory.call_args.kwargs["ssl_context"].verify_mode, ssl.CERT_REQUIRED)
            self.assertFalse(pool.urlopen.call_args.kwargs["redirect"])
            pool.urlopen.return_value = Mock(status=302, data=b'')
            with self.assertRaises(RuntimeError):
                application.mastodon_request("https://mastodon.social", "/api/v1/accounts/verify_credentials", "test")

    def test_stats_count_cached_mail_and_ignore_other_users_and_invalid_entries(self):
        with application.app.app_context():
            user = {'id': self.user_id}
            self.assertEqual(application.cached_mail_stats(user), dict(total=0, unread=0, starred=0, sent=0))
            application.gmail_cache_put(self.user_id, 'inbox', metadata={
                'unread': True, 'starred': True, 'label_ids': ['INBOX'],
            })
            application.gmail_cache_put(self.user_id, 'sent', metadata={
                'unread': False, 'starred': False, 'label_ids': ['SENT'],
            })
            application.gmail_cache_put(self.user_id + 1, 'sent', metadata={'label_ids': ['SENT']})
            application.get_db().execute(
                "INSERT INTO gmail_cache (user_id, message_id, metadata) VALUES (?, 'invalid', 'broken')",
                (self.user_id,),
            )
            self.assertEqual(application.cached_mail_stats(user), dict(total=2, unread=1, starred=1, sent=1))

    def test_whatsapp_webhook_stores_inbound_message(self):
        self.save_whatsapp()
        response = self.signed_webhook(
            "/integrations/whatsapp/webhook",
            json={
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "123456789012345"},
                                    "messages": [
                                        {
                                            "id": "wamid.test-1",
                                            "from": "233201234567",
                                            "timestamp": "1700000000",
                                            "text": {"body": "Hello CentroMail"},
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        with application.app.app_context():
            messages = application.whatsapp_recent_messages(self.user_id)
        self.assertEqual(messages[0]["text"], "Hello CentroMail")
        self.assertEqual(messages[0]["sender"], "233201234567")

    def test_invalid_telegram_start_is_rejected_without_network(self):
        response = self.post_form(
            "/integrations/telegram/start",
            {"api_id": "not-a-number", "api_hash": "x", "phone": "123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"numeric API ID", response.data)

    def test_invalid_discord_form_is_rejected_without_network(self):
        response = self.post_form(
            "/integrations/discord",
            {"bot_token": "short", "channel_id": "123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"valid Discord bot token", response.data)


if __name__ == "__main__":
    unittest.main()
