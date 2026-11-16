"""Integration page and webhook tests using a disposable SQLite database."""

import json
import hashlib
import hmac
import ssl
from unittest.mock import Mock, patch
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

import app as application


class IntegrationFixture(unittest.TestCase):
    def setUp(self):
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
            self.assertIn(b'data-integration-feed', response.data)
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

    def test_stats_do_not_invent_sent_messages(self):
        self.assertEqual(application.make_stats([])["sent"], 0)
        self.assertEqual(application.make_stats([{"unread":False,"starred":False,"label_ids":["SENT"]}])["sent"], 1)

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
