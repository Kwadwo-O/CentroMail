"""Integration page and webhook tests using a disposable SQLite database."""

import json
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

import app as application


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.previous_config = {
            key: application.app.config.get(key)
            for key in ("DATABASE", "TESTING", "SECRET_KEY")
        }
        self.addCleanup(application.app.config.update, self.previous_config)
        application.app.config.update(
            DATABASE=str(Path(self.directory.name) / "test.sqlite"),
            TESTING=True,
            SECRET_KEY="test-only-secret",
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

    def test_whatsapp_webhook_stores_inbound_message(self):
        self.save_whatsapp()
        response = self.client.post(
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
