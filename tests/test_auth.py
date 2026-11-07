"""Authentication integration tests using a separate, disposable SQLite database.

Run from the project root with ``python -m unittest discover -s tests -v``.
"""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

from werkzeug.security import check_password_hash, generate_password_hash

import app as application


class AuthTests(unittest.TestCase):
    password = "correct horse battery staple"

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
        for route in ("/dashboard", "/inbox", "/mail", "/message/1", "/compose", "/settings"):
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
        routes = ("/dashboard", "/inbox", "/mail", "/message/1", "/compose", "/settings")
        for route in routes:
            with self.subTest(route=route):
                self.assert_redirect_path(self.client.get(route), "/login")
        self.register()
        self.post("/logout", {})
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)
        self.assert_redirect_path(self.client.get("/dashboard"), "/login")

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

    def test_logout_and_compose_require_csrf_without_revoking_valid_session(self):
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
