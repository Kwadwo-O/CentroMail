"""Authentication integration tests using a separate, disposable SQLite database.

Run from the project root with ``python -m unittest discover -s tests -v``.
"""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlparse

from werkzeug.security import check_password_hash, generate_password_hash

import app as application
import requests


class AuthTests(unittest.TestCase):
    password = "correct horse battery staple"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.previous_config = {
            key: application.app.config.get(key)
            for key in (
                "DATABASE", "TESTING", "SECRET_KEY", "GOOGLE_CLIENT_ID",
                "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI",
            )
        }
        self.addCleanup(application.app.config.update, self.previous_config)
        application.app.config.update(
            DATABASE=str(Path(self.directory.name) / "test.sqlite"),
            TESTING=True,
            SECRET_KEY="test-only-secret",
            GOOGLE_CLIENT_ID=None,
            GOOGLE_CLIENT_SECRET=None,
            GOOGLE_REDIRECT_URI=None,
        )
        with application.app.app_context():
            application.init_db()
        self.client = application.app.test_client()

    def post(self, path, data, client=None, **kwargs):
        """Submit a real CSRF-protected form as a browser would."""
        client = client or self.client
        client.get("/login", follow_redirects=True)
        with client.session_transaction() as session:
            token = session["csrf_token"]
        return client.post(path, data={**data, "csrf_token": token}, **kwargs)

    def register(self, **overrides):
        data = {
            "name": "Test Person",
            "email": "person@example.com",
            "password": self.password,
            "confirm_password": self.password,
        }
        data.update(overrides)
        return self.post("/register", data)

    def assert_redirect_path(self, response, path):
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlparse(response.headers["Location"]).path, path)

    def users(self):
        with application.app.app_context():
            return application.get_db().execute("SELECT * FROM users ORDER BY id").fetchall()

    def test_auth_pages_and_local_assets_load(self):
        for route in ("/login", "/register", "/onboarding"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'/static/css/login.css', response.data)
                self.assertIn(b'name="csrf_token"', response.data)
        for route in (
            "/static/css/login.css",
            "/static/images/Logo_clear.png",
        ):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_landing_is_public_and_keeps_account_actions_available(self):
        with patch.object(application.google_requests, 'get', side_effect=AssertionError('Landing must not load email')):
            response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'All your conversations.', response.data)
        self.assertIn(b'href="/register"', response.data)
        self.assertIn(b'href="/login"', response.data)
        self.assertNotIn(b'Log out', response.data)
        self.register()
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/dashboard"', response.data)
        self.assertNotIn(b'href="/register"', response.data)

    def test_register_persists_normalized_email_and_hashed_password(self):
        response = self.register(name="  Test Person  ", email="  Person@Example.COM  ")
        self.assert_redirect_path(response, "/dashboard")
        users = self.users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["email"], "person@example.com")
        self.assertEqual(users[0]["name"], "Test Person")
        self.assertNotEqual(users[0]["password"], self.password)
        self.assertTrue(check_password_hash(users[0]["password"], self.password))
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], users[0]["id"])
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_duplicate_email_does_not_overwrite_account(self):
        self.register()
        self.post("/logout", {})
        response = self.register(
            name="Another Person", email="PERSON@EXAMPLE.COM", password="different secret password",
            confirm_password="different secret password",
        )
        if response.status_code == 302:
            response = self.client.get(response.headers["Location"])
        self.assertIn(response.status_code, (200, 400))
        users = self.users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["name"], "Test Person")
        self.assertTrue(check_password_hash(users[0]["password"], self.password))
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_invalid_registration_never_creates_a_user(self):
        cases = (
            {"name": " "},
            {"email": "not-an-email"},
            {"password": "short", "confirm_password": "short"},
            {"confirm_password": "different password"},
            {"confirm_password": ""},
        )
        for data in cases:
            with self.subTest(data=list(data)):
                response = self.register(**data)
                self.assertIn(response.status_code, (200, 400))
                self.assertTrue(response.data)
                self.assertEqual(self.users(), [])
                with self.client.session_transaction() as session:
                    self.assertNotIn("user_id", session)

    def test_wrong_password_and_unknown_email_cannot_authenticate(self):
        self.register()
        self.post("/logout", {})
        for email in ("person@example.com", "missing@example.com"):
            with self.subTest(email=email):
                response = self.post("/login", {"email": email, "password": "wrong password"})
                self.assertIn(response.status_code, (200, 400))
                with self.client.session_transaction() as session:
                    self.assertNotIn("user_id", session)
                self.assert_redirect_path(self.client.get("/dashboard"), "/login")

    def test_account_survives_logout_and_new_browser_session(self):
        self.register()
        self.assert_redirect_path(self.post("/logout", {}), "/login")
        fresh_browser = application.app.test_client()
        response = self.post(
            "/login",
            {"email": "PERSON@EXAMPLE.COM", "password": self.password},
            client=fresh_browser,
        )
        self.assert_redirect_path(response, "/dashboard")
        for route in ("/dashboard", "/inbox", "/mail", "/message/1", "/settings"):
            with self.subTest(route=route):
                self.assertEqual(fresh_browser.get(route).status_code, 200)

    def test_remember_me_sets_permanent_session_only_when_selected(self):
        self.register()
        for remember in ("on", ""):
            with self.subTest(remember=remember):
                self.post("/logout", {})
                response = self.post("/login", {
                    "email": "person@example.com", "password": self.password, "remember": remember,
                })
                self.assert_redirect_path(response, "/dashboard")
                with self.client.session_transaction() as session:
                    self.assertEqual(session.permanent, bool(remember))

    def test_private_pages_require_login_and_logout_revokes_access(self):
        routes = ("/dashboard", "/inbox", "/mail", "/message/1", "/settings")
        for route in routes:
            with self.subTest(route=route):
                self.assert_redirect_path(self.client.get(route), "/login")
        self.register()
        self.post("/logout", {})
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)
        self.assert_redirect_path(self.client.get("/dashboard"), "/login")

    def test_manual_inbox_refresh_finds_new_mail_with_a_fresh_cached_list(self):
        self.register()
        message = self.mail_metadata("new-message")
        response = Mock()
        response.json.return_value = {"messages": []}
        with (
            patch.object(application, "get_gmail_access_token", return_value="test-token"),
            patch.object(application.google_requests, "get", return_value=response) as list_mail,
            patch.object(application, "_fetch_gmail_detail", return_value=message) as detail,
        ):
            self.assertEqual(self.client.get("/api/mail/messages").json["count"], 0)
            response.json.return_value = {"messages": [{"id": message["id"]}]}
            self.assertEqual(self.client.get("/api/mail/messages").json["count"], 0)
            self.assertEqual(list_mail.call_count, 1)
            refreshed = self.client.get("/api/mail/messages?refresh=1")
            self.assertEqual(refreshed.status_code, 200)
            self.assertIn(message["subject"], refreshed.json["html"])
            self.assertEqual(list_mail.call_count, 2)
            detail.assert_called_once()
            self.assertEqual(self.client.get("/api/mail/messages").json["count"], 1)
            self.assertEqual(list_mail.call_count, 2)

    @staticmethod
    def mail_metadata(message_id, labels=None):
        labels = labels if labels is not None else ["INBOX", "UNREAD"]
        return {"id": message_id, "sender": "Test Sender", "email": "sender@example.com",
                "thread_id": "thread-" + message_id, "reply_to": "", "to": "person@example.com", "message_id": "<" + message_id + "@example.com>", "references": "",
                "subject": "Subject " + message_id, "preview": "Message preview", "time": "Nov 15",
                "date": "Nov 15, 2026", "internal_date": 123, "label_ids": labels,
                "unread": "UNREAD" in labels, "starred": "STARRED" in labels, "category": "primary"}

    def test_inbox_renders_only_a_small_cached_preview_without_network(self):
        self.register()
        with application.app.app_context():
            for index in range(40):
                application.gmail_cache_put(self.users()[0]["id"], str(index), metadata=self.mail_metadata(str(index)))
        with patch.object(application, "get_gmail_access_token") as token:
            response = self.client.get("/inbox")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data.count(b'class="message unread"'), application.MAIL_BATCH_SIZE)
            token.assert_not_called()

    def test_mail_folders_and_cursor_load_only_the_requested_gmail_page(self):
        self.register()
        response = Mock()
        response.json.return_value = {"messages": [{"id": "sample"}], "nextPageToken": "next-page", "resultSizeEstimate": 3370}
        with (
            patch.object(application, "get_gmail_access_token", return_value="test-token"),
            patch.object(application.google_requests, "get", return_value=response) as list_mail,
            patch.object(application, "_fetch_gmail_detail", return_value=self.mail_metadata("sample")),
        ):
            for folder, config in application.GMAIL_FOLDERS.items():
                with self.subTest(folder=folder):
                    shell = self.client.get("/inbox?folder=" + folder)
                    self.assertEqual(shell.status_code, 200)
                    result = self.client.get("/api/mail/messages?folder=" + folder)
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json["next_cursor"], "next-page")
                    params = list_mail.call_args.kwargs["params"]
                    self.assertEqual(params["maxResults"], application.MAIL_BATCH_SIZE)
                    self.assertNotIn("pageToken", params)
                    self.assertEqual(params.get("labelIds"), config.get("label"))
                    self.assertEqual(params.get("q", ""), config.get("query", ""))
            self.assertEqual(list_mail.call_count, len(application.GMAIL_FOLDERS))
            self.client.get("/api/mail/messages?cursor=next-page")
            self.assertEqual(list_mail.call_args.kwargs["params"]["pageToken"], "next-page")
            self.assertEqual(self.client.get("/api/mail/messages?folder=unknown").status_code, 404)

    def test_message_actions_require_csrf_and_update_gmail_and_local_metadata(self):
        self.register()
        user_id = self.users()[0]["id"]
        with application.app.app_context():
            application.gmail_cache_put(user_id, "sample", metadata=self.mail_metadata("sample"))
        self.assertEqual(self.client.post("/api/mail/action", data={"action": "read", "message_ids": "sample"}).status_code, 400)
        with (
            patch.object(application, "get_gmail_access_token", return_value="test-token"),
            patch.object(application.google_requests, "post", return_value=Mock()) as modify,
        ):
            for action, add, remove in (("star", ["STARRED"], []), ("read", [], ["UNREAD"]), ("archive", [], ["INBOX"]), ("trash", ["TRASH"], ["INBOX"]), ("restore", ["INBOX"], ["TRASH"])):
                result = self.post("/api/mail/action", {"action": action, "message_ids": "sample"})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(modify.call_args.kwargs["json"], {"ids": ["sample"], "addLabelIds": add, "removeLabelIds": remove})
                with application.app.app_context():
                    labels = application.gmail_cache_get(user_id, "sample")["label_ids"]
                    for label in add: self.assertIn(label, labels)
                    for label in remove: self.assertNotIn(label, labels)

    def test_formatted_message_body_survives_cache_and_renders_in_isolated_reader(self):
        self.register()
        user_id = self.users()[0]["id"]
        body = {"text": "Hello", "html": '<p style="font-size:20px">Hello</p>'}
        with application.app.app_context():
            application.gmail_cache_put(user_id, "sample", metadata=self.mail_metadata("sample"), body=body)
            self.assertEqual(application.gmail_cache_get(user_id, "sample", body=True), body)
        with patch.object(application.google_requests, "get") as network:
            for path in ("/message/sample?folder=sent", "/message/sample?folder=sent&pane=1"):
                result = self.client.get(path)
                self.assertEqual(result.status_code, 200)
                self.assertIn(b'class="email-body-frame"', result.data)
                self.assertIn(b'sandbox="allow-popups allow-popups-to-escape-sandbox"', result.data)
            network.assert_not_called()

    def test_legal_pages_are_public_and_linked(self):
        for route, heading in (("/privacy", b"Privacy Notice"), ("/terms", b"Terms of Use")):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn(heading, response.data)
                self.assertIn(b"support@centromail.net", response.data)

    def test_account_delete_removes_local_account_data(self):
        self.register()
        with application.app.app_context():
            db = application.get_db()
            user_id = db.execute("SELECT id FROM users WHERE email = ?", ("person@example.com",)).fetchone()["id"]
            db.execute("INSERT INTO integrations(user_id, provider, config, updated_at) VALUES (?, ?, ?, ?)",
                       (user_id, "telegram", "{}", 1))
            db.execute("INSERT INTO whatsapp_messages(user_id, message_id, body, received_at) VALUES (?, ?, ?, ?)",
                       (user_id, "message-1", "private", 1))
            db.commit()
        response = self.post("/account/delete", {})
        self.assert_redirect_path(response, "/login")
        with application.app.app_context():
            db = application.get_db()
            self.assertIsNone(db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone())
            self.assertIsNone(db.execute("SELECT user_id FROM integrations WHERE user_id = ?", (user_id,)).fetchone())
            self.assertIsNone(db.execute("SELECT user_id FROM whatsapp_messages WHERE user_id = ?", (user_id,)).fetchone())

    def test_onboarding_selects_login_or_registration(self):
        self.register()
        self.post("/logout", {})
        for email, destination in (
            ("PERSON@EXAMPLE.COM", "/login"),
            ("new@example.com", "/register"),
        ):
            with self.subTest(email=email):
                response = self.post("/continue", {"email": email})
                self.assert_redirect_path(response, destination)
                page = self.client.get(response.headers["Location"])
                self.assertEqual(page.status_code, 200)
                self.assertIn(email.lower().encode(), page.data)
        response = self.post("/continue", {"email": "invalid"}, follow_redirects=True)
        self.assertIn(response.status_code, (200, 400))
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_missing_or_wrong_csrf_token_rejects_authentication_posts(self):
        self.client.get("/login")
        for route, data in (
            ("/continue", {"email": "person@example.com"}),
            ("/login", {"email": "person@example.com", "password": self.password}),
            ("/register", {
                "name": "Test Person", "email": "person@example.com", "password": self.password,
                "confirm_password": self.password,
            }),
        ):
            for token in (None, "invalid-token", "\u2603"):
                with self.subTest(route=route, token=token):
                    body = dict(data)
                    if token is not None:
                        body["csrf_token"] = token
                    response = self.client.post(route, data=body)
                    self.assertEqual(response.status_code, 400)
        self.assertEqual(self.users(), [])

    def test_removed_database_account_invalidates_saved_session(self):
        self.register()
        with application.app.app_context():
            db = application.get_db()
            db.execute("DELETE FROM users")
            db.commit()
        self.assert_redirect_path(self.client.get("/dashboard"), "/login")

    def test_logout_and_send_require_csrf_without_revoking_valid_session(self):
        self.register()
        for route in ("/logout", "/compose"):
            with self.subTest(route=route):
                response = self.client.post(route, data={"csrf_token": "wrong-token"})
                self.assertEqual(response.status_code, 400)
                with self.client.session_transaction() as session:
                    self.assertIn("user_id", session)
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assert_redirect_path(self.post("/logout", {}), "/login")

    def test_provider_buttons_never_create_placeholder_login(self):
        for provider in ("google", "microsoft"):
            with self.subTest(provider=provider):
                response = self.client.get(f"/auth/{provider}", follow_redirects=True)
                self.assertIn(response.status_code, (200, 503))
                with self.client.session_transaction() as session:
                    self.assertNotIn("user_id", session)
                    self.assertNotIn("user_email", session)

    def test_google_sign_in_starts_oauth_with_configured_callback(self):
        application.app.config.update(
            GOOGLE_CLIENT_ID="test-client-id",
            GOOGLE_CLIENT_SECRET="test-client-secret",
            GOOGLE_REDIRECT_URI="https://example.test/auth/google/callback",
        )
        with patch.object(
            application.google, "authorize_redirect", return_value=application.redirect("/google")
        ) as authorize_redirect:
            response = self.client.get("/auth/google")
        self.assert_redirect_path(response, "/google")
        authorize_redirect.assert_called_once_with("https://example.test/auth/google/callback")

    def test_google_callback_creates_verified_account_and_signs_in(self):
        application.app.config.update(
            GOOGLE_CLIENT_ID="test-client-id",
            GOOGLE_CLIENT_SECRET="test-client-secret",
        )
        with patch.object(application.google, "authorize_access_token", return_value={
            "userinfo": {
                "sub": "google-user-id",
                "email": "Person@Example.com",
                "email_verified": True,
                "name": "Test Person",
            },
        }):
            response = self.client.get("/auth/google/callback")
        self.assert_redirect_path(response, "/dashboard")
        users = self.users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["email"], "person@example.com")
        self.assertEqual(users[0]["name"], "Test Person")
        self.assertNotEqual(users[0]["password"], self.password)
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], users[0]["id"])

    def test_google_redirect_does_not_wait_for_discovery(self):
        application.app.config.update(GOOGLE_CLIENT_ID="test-client-id", GOOGLE_CLIENT_SECRET="test-client-secret")
        with patch('requests.sessions.Session.request', side_effect=AssertionError('Sign-in must not fetch discovery metadata')):
            response = self.client.get('/auth/google')
        location = urlparse(response.location)
        self.assertEqual(location.netloc, 'accounts.google.com')
        self.assertEqual(location.path, '/o/oauth2/v2/auth')
        self.assertIn('state=', location.query)
        with application.google._get_session() as client:
            self.assertEqual(client.default_timeout, (5, 15))

    def test_google_starts_on_local_callback_host_before_saving_state(self):
        application.app.config.update(GOOGLE_CLIENT_ID="test-client-id", GOOGLE_CLIENT_SECRET="test-client-secret",
                                      GOOGLE_REDIRECT_URI="http://localhost:5000/auth/google/callback")
        with patch.object(application.google, 'authorize_redirect') as authorize:
            response = self.client.get('/auth/google', base_url='http://127.0.0.1:5000')
        self.assertEqual(response.location, 'http://localhost:5000/auth/google')
        authorize.assert_not_called()

    def test_google_network_failure_returns_to_login_with_retry_message(self):
        application.app.config.update(GOOGLE_CLIENT_ID="test-client-id", GOOGLE_CLIENT_SECRET="test-client-secret")
        for path, method in (('/auth/google', 'authorize_redirect'), ('/auth/google/callback?code=test', 'authorize_access_token')):
            with self.subTest(path=path), patch.object(application.google, method, side_effect=requests.Timeout('Network timeout')):
                response = self.client.get(path, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'try', response.data.lower())
            with self.client.session_transaction() as session:
                self.assertNotIn('user_id', session)

    def test_google_token_and_signing_key_requests_use_ipv4_with_tls_verification(self):
        for client in (application.google._get_session(), application.google._get_oauth_client()):
            with client:
                self.assertTrue(client.verify)
                self.assertEqual(client.default_timeout, (5, 15))
                for url in ('https://oauth2.googleapis.com/token', 'https://www.googleapis.com/oauth2/v3/certs'):
                    adapter = client.get_adapter(url)
                    self.assertEqual(adapter.poolmanager.connection_pool_kw['source_address'], ('0.0.0.0', 0))

    def test_google_callback_rejects_unverified_email(self):
        application.app.config.update(
            GOOGLE_CLIENT_ID="test-client-id",
            GOOGLE_CLIENT_SECRET="test-client-secret",
        )
        with patch.object(application.google, "authorize_access_token", return_value={
            "userinfo": {
                "sub": "google-user-id",
                "email": "person@example.com",
                "email_verified": False,
                "name": "Test Person",
            },
        }):
            response = self.client.get("/auth/google/callback")
        self.assert_redirect_path(response, "/onboarding")
        self.assertEqual(self.users(), [])

    def test_existing_database_schema_migrates_without_losing_login(self):
        legacy_database = str(Path(self.directory.name) / "legacy.sqlite")
        with closing(sqlite3.connect(legacy_database)) as db, db:
            db.execute("""CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
            db.execute(
                "INSERT INTO users(email, password) VALUES (?, ?)",
                ("Legacy@Example.com", generate_password_hash(self.password)),
            )
        application.app.config["DATABASE"] = legacy_database
        with application.app.app_context():
            application.init_db()
            columns = application.get_db().execute("PRAGMA table_info(users)").fetchall()
            self.assertIn("name", [column["name"] for column in columns])
        response = self.post("/login", {"email": "legacy@example.com", "password": self.password})
        self.assert_redirect_path(response, "/dashboard")
        self.assertEqual(len(self.users()), 1)


if __name__ == "__main__":
    unittest.main()
