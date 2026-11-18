import os
import hashlib
import hmac
import ipaddress
import socket
import ssl
import urllib3
import asyncio
import json
import base64
import html
import logging
import re
import mimetypes
import secrets
import sqlite3
import threading
import time
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.message import EmailMessage
from email.utils import parsedate_to_datetime, parseaddr, getaddresses
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import imaplib
import smtplib
import email_providers
import graph_mail
import graph_teams
import google_chat
import integration_catalog
from email_validation import email_address_error
from sender_logos import logo_cdn_enabled, sender_logo_source
import bleach
import tinycss2
from bleach.css_sanitizer import CSSSanitizer
from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.flask_client import OAuth
from itsdangerous import BadSignature, URLSafeSerializer
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from google_transport import GoogleOAuthApp, google_requests
from smart_cleanup import scan_promotions

try:
    from telethon import TelegramClient, errors as telegram_errors, functions as telegram_functions, types as telegram_types
    from telethon.errors import (
        ApiIdInvalidError,
        FloodWaitError,
        PasswordHashInvalidError,
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        PhoneNumberInvalidError,
        SessionPasswordNeededError,
    )
    from telethon.sessions import StringSession

    TELETHON_AVAILABLE = True
except ImportError:  # Keep the rest of CentroMail usable without Telethon.
    TelegramClient = None
    StringSession = None
    TELETHON_AVAILABLE = False

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
load_dotenv(Path(app.root_path) / ".env")
DATABASE = os.path.join(app.root_path, "centro.db")
app.config.update(
    DATABASE=os.environ.get("CENTROMAIL_DATABASE", DATABASE),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("CENTROMAIL_COOKIE_SECURE") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=1024 * 1024,
    MICROSOFT_CLIENT_ID=os.environ.get("MICROSOFT_CLIENT_ID"),
    MICROSOFT_CLIENT_SECRET=os.environ.get("MICROSOFT_CLIENT_SECRET"),
    MICROSOFT_TENANT=os.environ.get("MICROSOFT_TENANT", "common"),
    MICROSOFT_REDIRECT_URI=os.environ.get("MICROSOFT_REDIRECT_URI"),
    MICROSOFT_TEAMS_REDIRECT_URI=os.environ.get("MICROSOFT_TEAMS_REDIRECT_URI"),
    WHATSAPP_APP_SECRET=os.environ.get("WHATSAPP_APP_SECRET"),
    GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID"),
    GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET"),
    GOOGLE_REDIRECT_URI=os.environ.get("GOOGLE_REDIRECT_URI"),
    CDN_PUBLIC_KEY=os.environ.get("CDN_PUBLIC_KEY"),
)
oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_cls=GoogleOAuthApp,
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    # Google's stable OIDC endpoints let sign-in redirect immediately, without
    # a discovery request before the browser can open the consent screen.
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    access_token_url="https://oauth2.googleapis.com/token",
    jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
    issuer="https://accounts.google.com",
    userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
    id_token_signing_alg_values_supported=["RS256"],
    client_kwargs={
        "scope": "openid email profile https://www.googleapis.com/auth/gmail.modify",
        "default_timeout": (5, 15),
    },
    authorize_params={"access_type": "offline", "prompt": "consent"},
)

microsoft_tenant = app.config["MICROSOFT_TENANT"]
if not re.fullmatch(r"[A-Za-z0-9.-]+", microsoft_tenant):
    raise ValueError("MICROSOFT_TENANT must be a tenant ID or common, consumers, or organizations.")
microsoft = oauth.register(name="microsoft", client_id=app.config["MICROSOFT_CLIENT_ID"],
    client_secret=app.config["MICROSOFT_CLIENT_SECRET"],
    authorize_url=f"https://login.microsoftonline.com/{microsoft_tenant}/oauth2/v2.0/authorize",
    access_token_url=f"https://login.microsoftonline.com/{microsoft_tenant}/oauth2/v2.0/token",
    client_kwargs={"scope":"offline_access https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send", "default_timeout":(5,20)})
teams_oauth = oauth.register(name='teams', client_id=app.config['MICROSOFT_CLIENT_ID'],
    client_secret=app.config['MICROSOFT_CLIENT_SECRET'],
    authorize_url=f'https://login.microsoftonline.com/{microsoft_tenant}/oauth2/v2.0/authorize',
    access_token_url=f'https://login.microsoftonline.com/{microsoft_tenant}/oauth2/v2.0/token',
    client_kwargs={'scope': graph_teams.SCOPES, 'default_timeout': (5,20)})


def load_secret_key():
    """Keep local sessions valid after a restart without a shared default key."""
    configured_key = os.environ.get("SECRET_KEY")
    if configured_key:
        return configured_key
    secret_file = Path(app.instance_path) / ".secret_key"
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with secret_file.open("x", encoding="utf-8") as handle:
            key = secrets.token_hex(32)
            handle.write(key)
            return key
    except FileExistsError:
        return secret_file.read_text(encoding="utf-8").strip()


app.secret_key = load_secret_key()

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    """Create the account store and upgrade the original users table in place."""
    with closing(sqlite3.connect(app.config["DATABASE"], timeout=10)) as db, db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                avatar_url TEXT,
                google_token TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        columns = {column[1] for column in db.execute("PRAGMA table_info(users)")}
        if "name" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''")
        if "avatar_url" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
        if "google_token" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN google_token TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (lower(email))")
        db.execute(
            """CREATE TABLE IF NOT EXISTS gmail_cache (
                user_id INTEGER NOT NULL,
                message_id TEXT NOT NULL,
                metadata TEXT,
                metadata_at REAL,
                body TEXT,
                body_at REAL,
                PRIMARY KEY (user_id, message_id)
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS integrations (
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                config TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, provider)
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS gmail_sync_state (
                user_id INTEGER PRIMARY KEY,
                message_ids TEXT NOT NULL,
                listed_at REAL NOT NULL
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS gmail_folder_pages (
                user_id INTEGER NOT NULL,
                folder TEXT NOT NULL,
                query TEXT NOT NULL,
                cursor TEXT NOT NULL,
                message_ids TEXT NOT NULL,
                next_cursor TEXT,
                total INTEGER NOT NULL,
                listed_at REAL NOT NULL,
                PRIMARY KEY (user_id, folder, query, cursor)
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS gmail_mailbox_counts (
                user_id INTEGER PRIMARY KEY,
                counts TEXT NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS whatsapp_messages (
                user_id INTEGER NOT NULL,
                message_id TEXT NOT NULL,
                sender TEXT,
                body TEXT,
                received_at REAL NOT NULL,
                PRIMARY KEY (user_id, message_id)
            )"""
        )
        db.execute("""CREATE TABLE IF NOT EXISTS gmail_account_counts (
            user_id INTEGER NOT NULL, account_key TEXT NOT NULL, counts TEXT NOT NULL,
            updated_at REAL NOT NULL, PRIMARY KEY (user_id, account_key))""")


with app.app_context():
    init_db()


def normalize_email(email):
    return email.strip().lower()


def valid_email(email):
    return not email_address_error(email)


# Password policy: at least one uppercase letter, one digit, one special
# character, 12-1024 characters, and not an easily guessed string.
COMMON_PASSWORDS = frozenset({
    "password", "password1", "password12", "password123", "password1234",
    "passw0rd", "p@ssw0rd", "p@ssword", "passwort", "motdepasse", "contrasena",
    "123456", "1234567", "12345678", "123456789", "1234567890", "123456789a",
    "qwerty", "qwerty123", "qwertyuiop", "abc123", "abcd1234", "letmein",
    "letmein123", "welcome", "welcome1", "welcome123", "admin", "admin123",
    "administrator", "iloveyou", "sunshine", "monkey", "dragon", "football",
    "baseball", "princess", "trustno1", "master", "shadow", "superman",
    "batman", "starwars", "whatever", "freedom", "changeme", "secret",
    "login", "access", "flower", "hello123", "charlie", "donald", "hunter2",
})

PASSWORD_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def new_password_error(password, email="", name=""):
    """Return a user-facing message when a new password fails policy, else None."""
    if not 12 <= len(password) <= 1024:
        return "Use between 12 and 1024 characters for your password."
    if not re.search(r"[A-Z]", password):
        return "Your password needs at least one uppercase letter."
    if not re.search(r"[0-9]", password):
        return "Your password needs at least one number."
    if not PASSWORD_SPECIAL.search(password):
        return "Your password needs at least one special character."
    lowered = password.lower()
    # Catch common bases with trivial trailing/leading digits or symbols,
    # e.g. "Password1234!" or "!qwerty2024".
    normalized = re.sub(r'^[^a-z]+|[^a-z]+$', '', lowered)
    if lowered in COMMON_PASSWORDS or normalized in COMMON_PASSWORDS:
        return "That password is too common. Choose something harder to guess."
    for token in (str(email).split("@")[0].lower(), str(name).strip().lower()):
        if len(token) >= 4 and token in lowered:
            return "Do not include your name or email address in your password."
    return None


def find_user(email):
    return get_db().execute(
        "SELECT * FROM users WHERE lower(email) = ?", (normalize_email(email),)
    ).fetchone()


PREFERENCE_GROUPS = json.loads((Path(app.root_path) / "static/preferences.json").read_text())


@app.context_processor
def appearance_context():
    return {"preference_groups": PREFERENCE_GROUPS,
            "logo_provider_enabled": logo_cdn_enabled(app.config.get('CDN_PUBLIC_KEY'))}


@app.template_global()
def sender_logo_url(email, local_only=False):
    key = None if local_only else app.config.get('CDN_PUBLIC_KEY')
    source = sender_logo_source(email, key)
    if not source:
        return None
    return source if source.startswith('https://img.logo.dev/') else url_for('static', filename=source)


@app.template_global()
def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


PROTECTED_ENDPOINTS = {
    'check_integration',
    "home", "dashboard", "inbox", "mail", "message_detail", "compose", "settings",
    "cleanup", "cleanup_promotions", "cleanup_promotion_details", "cleanup_gmail_refresh",
    "cleanup_trash_promotions",
    "mailbox_messages", "mailbox_counts", "mail_action",
    "gmail_message_states", "mail_conversation",
    "delete_account",
    "integrations", "telegram_start_route", "telegram_verify_route",
    "telegram_password_route", "telegram_restart_route", "test_telegram_route",
    "disconnect_telegram_route", "connect_whatsapp_route", "test_whatsapp_route",
    "disconnect_whatsapp_route", "connect_discord_route", "test_discord_route",
    "disconnect_discord_route", "connect_social_route", "test_social_route",
    "disconnect_social_route", "integration_messages", "connect_email", "disconnect_email", "microsoft_callback",
    "telegram_chat_route", "telegram_photo_route", "telegram_media_route",
    "telegram_message_action_route",
    "teams_connect", "teams_callback", "teams_disconnect", "teams_conversations", "teams_messages",
    "google_chat_connect", "google_chat_disconnect", "google_chat_spaces", "google_chat_messages",
    "google_chat_action", "google_chat_upload", "google_chat_attachment",
}


@app.before_request
def load_user_and_check_forms():
    if request.endpoint == 'google_chat_upload': request.max_content_length = google_chat.FILE_LIMIT + 64 * 1024
    user_id = session.get("user_id")
    g.user = (
        get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user_id is not None else None
    )
    if user_id is not None and g.user is None:
        session.clear()
    if request.endpoint in PROTECTED_ENDPOINTS and g.user is None:
        return redirect(url_for("login"))
    if request.method == "POST" and request.endpoint != "whatsapp_webhook":
        expected = session.get("csrf_token", "")
        submitted = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected.encode('utf-8'), submitted.encode('utf-8')):
            abort(400, description="Your form has expired. Go back, refresh the page, and try again.")


@app.after_request
def prevent_cached_account_pages(response):
    if request.endpoint in PROTECTED_ENDPOINTS or request.endpoint in {
        "login", "register", "onboarding",
    }:
        response.headers["Cache-Control"] = "no-store"
    return response


def sign_in(user, remember=False):
    session.clear()
    session["user_id"] = user["id"]
    session["user_email"] = user["email"]
    session.permanent = remember


def render_auth(active_panel="login", email="", name="", remember=False, email_error=""):
    return render_template(
        "register.html" if active_panel == "signup" else "login.html",
        email=email, name=name, remember=remember, email_error=email_error,
    )


def email_accounts(user):
    accounts = []
    if get_google_token(user):
        accounts.append({"key":"gmail", "name":"Gmail", "email":user["email"], "kind":"gmail"})
    rows = get_db().execute("SELECT provider, config FROM integrations WHERE user_id = ? AND provider LIKE 'email:%'", (user["id"],)).fetchall()
    for row in rows:
        try:
            config = json.loads(row["config"])
        except (ValueError, TypeError):
            continue
        if isinstance(config, dict):
            accounts.append({"key":row["provider"], "name":config.get("name","Email"), "email":config.get("email",""), "kind":config.get("kind"), "config":config})
    return accounts


def active_email_account(user):
    accounts = email_accounts(user)
    requested = request.args.get("account") or request.form.get("account")
    if requested == "all":
        if request.endpoint not in {"inbox", "mail", "mailbox_messages", "mailbox_counts"}:
            abort(400)
        requested = None
    key = requested or session.get("mail_account")
    if requested and requested != "gmail" and not any(account["key"] == requested for account in accounts):
        abort(404)
    selected = next((account for account in accounts if account["key"] == key), None)
    if selected is None:
        selected = next((account for account in accounts if account["key"] == "gmail"), accounts[0] if accounts else {"key":"gmail","kind":"gmail","email":user["email"]})
    if request.endpoint in {'inbox', 'mail'} and request.args.get('account') != 'all':
        session["mail_account"] = selected["key"]
    return selected


def microsoft_access_token(account):
    config = account["config"]
    token = config["token"]
    if token.get("access_token") and token.get("expires_at",0) > time.time()+60:
        return token["access_token"]
    if not token.get("refresh_token"):
        raise RuntimeError("Reconnect Microsoft to refresh access.")
    response = requests.post(f"https://login.microsoftonline.com/{app.config['MICROSOFT_TENANT']}/oauth2/v2.0/token",
        data={"grant_type":"refresh_token","refresh_token":token["refresh_token"],"client_id":app.config["MICROSOFT_CLIENT_ID"],"client_secret":app.config["MICROSOFT_CLIENT_SECRET"]},timeout=(5,20))
    response.raise_for_status(); refreshed=response.json()
    token.update(refreshed); token["expires_at"]=time.time()+refreshed.get("expires_in",3600)
    save_integration(g.user["id"],account["key"],config)
    return token["access_token"]


def make_stats(messages):
    return {
        'total': len(messages),
        'unread': sum(1 for message in messages if message['unread']),
        'starred': sum(1 for message in messages if message['starred']),
        'sent': sum(1 for message in messages if 'SENT' in message.get('label_ids', [])),
    }


def store_google_token(user_id, token):
    get_db().execute(
        "UPDATE users SET google_token = ? WHERE id = ?",
        (json.dumps(token), user_id),
    )
    get_db().commit()


def get_google_token(user):
    if not user["google_token"]:
        return None
    try:
        token = json.loads(user["google_token"])
    except (TypeError, json.JSONDecodeError):
        return None
    return token if isinstance(token, dict) else None


def get_gmail_access_token(user, account=None, *, force_refresh=False):
    account = account or active_email_account(user)
    if account["kind"] != "gmail":
        return None
    token = account["config"]["token"] if account["key"] != "gmail" else get_google_token(user)
    if not token:
        return None
    expires_at = token.get("expires_at", 0)
    if not force_refresh and token.get("access_token") and expires_at > datetime.now(timezone.utc).timestamp() + 60:
        return token["access_token"]
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        return None
    response = google_requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": app.config["GOOGLE_CLIENT_ID"],
            "client_secret": app.config["GOOGLE_CLIENT_SECRET"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=(5, 15),
    )
    response.raise_for_status()
    refreshed = response.json()
    token["access_token"] = refreshed["access_token"]
    token["expires_at"] = datetime.now(timezone.utc).timestamp() + refreshed.get("expires_in", 3600)
    if account["key"] == "gmail":
        store_google_token(user["id"], token)
    else:
        account["config"]["token"] = token
        save_integration(user["id"], account["key"], account["config"])
    return token["access_token"]


def gmail_message_key(account, raw_id):
    return raw_id if account["key"] == "gmail" else "gm-" + account["config"]["account_id"] + "-" + raw_id


def gmail_raw_message_id(account, identifier):
    if account["key"] == "gmail":
        raw_id = identifier
        if raw_id.startswith(("gm-", "imap-", "ms-")):
            raise ValueError("This email belongs to a different account.")
    else:
        prefix = "gm-" + account["config"]["account_id"] + "-"
        if not identifier.startswith(prefix):
            raise ValueError("This email belongs to a different account.")
        raw_id = identifier[len(prefix):]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", raw_id):
        raise ValueError("Invalid Gmail message identifier.")
    return raw_id


def gmail_folder_key(account, folder):
    return folder if account["key"] == "gmail" else "gm:" + account["config"]["account_id"] + ":" + folder


GMAIL_METADATA_TTL = 12 * 60 * 60
GMAIL_BODY_TTL = 24 * 60 * 60
EMAIL_HTML_VERSION = 2


def gmail_cache_get(user_id, message_id, *, body=False):
    row = get_db().execute(
        "SELECT metadata, metadata_at, body, body_at FROM gmail_cache "
        "WHERE user_id = ? AND message_id = ?",
        (user_id, message_id),
    ).fetchone()
    if row is None:
        return None
    now = time.time()
    if body:
        if row["body"] is None or now - (row["body_at"] or 0) > GMAIL_BODY_TTL:
            return None
        try:
            decoded = json.loads(row["body"])
        except (TypeError, json.JSONDecodeError):
            return {"text": row["body"], "html": ""}
        if isinstance(decoded, dict) and decoded.get('html') and decoded.get('html_version') != EMAIL_HTML_VERSION:
            return None
        return decoded if isinstance(decoded, dict) else {"text": row["body"], "html": ""}
    if row["metadata"] is None or now - (row["metadata_at"] or 0) > GMAIL_METADATA_TTL:
        return None
    try:
        return json.loads(row["metadata"])
    except (TypeError, json.JSONDecodeError):
        return None


def gmail_cache_put(user_id, message_id, metadata=None, body=None):
    get_db().execute(
        """INSERT INTO gmail_cache
               (user_id, message_id, metadata, metadata_at, body, body_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id, message_id) DO UPDATE SET
               metadata = COALESCE(excluded.metadata, gmail_cache.metadata),
               metadata_at = COALESCE(excluded.metadata_at, gmail_cache.metadata_at),
               body = COALESCE(excluded.body, gmail_cache.body),
               body_at = COALESCE(excluded.body_at, gmail_cache.body_at)""",
        (
            user_id,
            message_id,
            json.dumps(metadata) if metadata is not None else None,
            time.time() if metadata is not None else None,
            json.dumps(body) if isinstance(body, dict) else body,
            time.time() if body is not None else None,
        ),
    )
    get_db().commit()


def gmail_error_status(error):
    response = getattr(error, "response", None)
    return response.status_code if response is not None else None


def gmail_error_reason(error):
    """Extract Google's machine-readable reason from an HTTP error."""
    response = getattr(error, "response", None)
    if response is None:
        return ""
    try:
        payload = response.json()
    except ValueError:
        return ""
    error_body = payload.get("error", {}) if isinstance(payload, dict) else {}
    reasons = [
        item.get("reason", "")
        for item in error_body.get("errors", [])
        if isinstance(item, dict)
    ]
    if error_body.get("status"):
        reasons.append(error_body["status"])
    if error_body.get("message"):
        reasons.append(error_body["message"])
    return " ".join(reasons).lower()


def gmail_error_message(error):
    reason = gmail_error_reason(error)
    if "quota" in reason or "ratelimit" in reason or "limit exceeded" in reason:
        return (
            "Gmail's API quota is temporarily exhausted. Wait about a minute, "
            "then refresh the page. CentroMail has cached messages it already loaded."
        )
    if "accessnotconfigured" in reason or "service_disabled" in reason or "disabled" in reason:
        return (
            "The Gmail API is disabled for this Google project. Enable it in Google Cloud "
            "Console, then sign in with Google again."
        )
    if "insufficient" in reason or "forbidden" in reason or "unauthorized" in reason:
        return (
            "Gmail access has expired or is missing permission. Sign in with Google again "
            "and allow access to Gmail."
        )
    return "Gmail could not be loaded right now. Please try again."


def gmail_cleanup_http_error(error, action):
    status = gmail_error_status(error)
    reason = gmail_error_reason(error)
    if status == 401:
        return jsonify(error="Gmail access expired.", refresh_required=True), 401
    if status == 429 or (
        status == 403
        and any(term in reason for term in ("quota", "ratelimit", "rate_limit", "limit exceeded"))
    ):
        return jsonify(
            error="Gmail is temporarily limiting requests. CentroMail will retry this scan.",
            retryable=True,
        ), 429
    if status == 403 and any(term in reason for term in ("insufficient", "forbidden", "unauthorized")):
        return jsonify(
            error=f"Gmail denied {action} because the connected account is missing permission.",
            reconnect=True,
        ), 403
    return jsonify(error=gmail_error_message(error)), status or 502


def fetch_cleanup_gmail_detail(headers, message_id):
    for attempt in range(3):
        try:
            return _fetch_gmail_detail(headers, message_id)
        except requests.HTTPError as error:
            status = gmail_error_status(error)
            reason = gmail_error_reason(error)
            rate_limited = status == 429 or (
                status == 403
                and any(term in reason for term in ("quota", "ratelimit", "rate_limit", "limit exceeded"))
            )
            if not rate_limited or attempt == 2:
                raise
            time.sleep(2 ** attempt)


def gmail_header(headers, name):
    return next(
        (header["value"] for header in headers if header.get("name", "").lower() == name.lower()),
        "",
    )


def gmail_sender(value):
    if "<" in value and value.endswith(">"):
        return value.rsplit("<", 1)[0].strip().strip('"') or value
    return value or "Unknown sender"


def gmail_sender_email(value):
    match = re.search(r"<([^>]+)>", value or "")
    return match.group(1).strip() if match else (value or "")


def gmail_message_time(value):
    try:
        return parsedate_to_datetime(value).astimezone().strftime("%b %d").replace(" 0", " ")
    except (TypeError, ValueError, OverflowError):
        return ""


@app.template_global()
def mail_list_time(message):
    try:
        when = datetime.strptime(message.get('date', ''), '%a, %b %d, %Y at %I:%M %p')
    except (TypeError, ValueError):
        try:
            when = datetime.fromtimestamp(message['internal_date'] / 1000, tz=timezone.utc).astimezone()
        except (KeyError, TypeError, ValueError, OSError, OverflowError):
            return message.get('time', '')
    if when.date() == datetime.now().astimezone().date():
        return when.strftime('%I:%M %p').lstrip('0')
    return message.get('time', '')


def gmail_message_full_time(value):
    try:
        when = parsedate_to_datetime(value).astimezone()
    except (TypeError, ValueError, OverflowError):
        return ""
    return when.strftime("%a, %b %d, %Y at %I:%M %p").replace(" 0", " ")


def gmail_message_date(metadata):
    """Return a full readable date for the message detail view."""
    if metadata.get("date"):
        return metadata["date"]
    internal_date = metadata.get("internal_date") or 0
    if internal_date:
        try:
            when = datetime.fromtimestamp(internal_date / 1000, tz=timezone.utc).astimezone()
        except (ValueError, OSError, OverflowError):
            pass
        else:
            return when.strftime("%a, %b %d, %Y at %I:%M %p").replace(" 0", " ")
    return metadata.get("time", "")


def email_html_text(source):
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", source)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>|</div\s*>|</tr\s*>", "\n", text)
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def decode_gmail_body(payload):
    """Return readable text and safe HTML from Gmail's nested MIME payload."""
    plain_parts = []
    html_parts = []

    def visit(part):
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime_type in {"text/plain", "text/html"}:
            try:
                decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                    "utf-8", errors="replace"
                )
            except (ValueError, UnicodeDecodeError):
                decoded = ""
            if mime_type == "text/plain":
                plain_parts.append(decoded)
            else:
                html_parts.append(decoded)
        for child in part.get("parts", []):
            visit(child)

    visit(payload or {})

    # Return plain text if available, else convert HTML to plain text.
    if plain_parts:
        plain_text = "\n\n".join(part.strip() for part in plain_parts if part.strip()).strip()
    elif html_parts:
        plain_text = email_html_text("\n".join(html_parts))
    else:
        plain_text = "(This email has no readable message body.)"

    # Produce a safe HTML version when the message has an HTML part.
    safe_html = ""
    if html_parts:
        combined_html = "\n".join(html_parts)
        email_css = CSSSanitizer(allowed_css_properties=[
            "color", "background-color", "font", "font-family", "font-size", "font-weight",
            "font-style", "line-height", "letter-spacing", "text-decoration", "text-align",
            "vertical-align", "white-space", "word-break", "overflow-wrap", "margin",
            "margin-top", "margin-bottom", "margin-left", "margin-right", "padding",
            "padding-top", "padding-bottom", "padding-left", "padding-right", "border",
            "border-top", "border-bottom", "border-left", "border-right", "border-color",
            "border-width", "border-style", "border-radius", "border-collapse", "border-spacing",
            "display", "width", "height", "min-width", "max-width", "min-height", "max-height",
            "table-layout", "list-style-type",
            "overflow", "overflow-x", "overflow-y", "visibility", "opacity", "mso-hide", "box-sizing",
        ])
        def clean_rules(css):
            rules = []
            for rule in tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True):
                if rule.type == "qualified-rule":
                    declarations = email_css.sanitize_css(tinycss2.serialize(rule.content))
                    if declarations:
                        rules.append(tinycss2.serialize(rule.prelude) + "{" + declarations + "}")
                elif rule.type == "at-rule" and rule.lower_at_keyword == "media" and rule.content:
                    rules.append("@media " + tinycss2.serialize(rule.prelude) + "{" + clean_rules(tinycss2.serialize(rule.content)) + "}")
            return "".join(rules)
        styles = "".join(clean_rules(css) for css in re.findall(r"(?is)<style[^>]*>(.*?)</style>", combined_html))
        # Preserve safe email typography and tables inside the isolated reader.
        combined_html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", combined_html)
        safe_html = bleach.clean(
            combined_html,
            tags=[
                "p", "br", "div", "span", "strong", "b", "em", "i", "u", "s", "strike",
                "a", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table",
                "thead", "tbody", "tr", "td", "th", "blockquote", "pre", "code", "hr",
                "img", "sub", "sup", "small", "mark", "del", "ins", "center", "caption", "colgroup", "col"
            ],
            attributes={
                "a": ["href", "title"],
                "img": ["src", "alt", "title", "width", "height"],
                "table": ["width", "align", "cellpadding", "cellspacing", "border"],
                "td": ["colspan", "rowspan", "width", "height", "align", "valign"],
                "th": ["colspan", "rowspan", "width", "align", "valign"],
                "*": ["class", "style", "id", "hidden"]
            },
            protocols=["http", "https", "mailto"],
            css_sanitizer=email_css,
            strip=True
        ).strip()
        if styles:
            safe_html = "<style>" + styles.replace("<", "\\3c ") + "</style>" + safe_html

    return {"text": plain_text, "html": safe_html, "html_version": EMAIL_HTML_VERSION}


def extract_otp_code(subject, text):
    """Return one unambiguous code next to explicit sign-in or verification wording."""
    marker = r"(?:one[\s-]*time[\s-]*(?:password|code|passcode)|otp|passcode|(?:verification|security|authentication|login|sign[\s-]*in|two[\s-]*factor|2fa)[\s-]*(?:code|pin))"
    code = r"(?<![A-Za-z0-9])(?:\d{3}[ -]\d{3}|\d{4,8}|[A-Za-z0-9]{6,8})(?![A-Za-z0-9])"
    content = html.unescape(subject + "\n" + (text or '')[:30000])
    content = re.split(r"(?im)^\s*(?:On .+ wrote:|[-]+\s*Original message\s*[-]+)", content)[0]
    candidates = []
    for pattern in (marker + r"(?:\s+is)?[\s:=\-–]*?(" + code + ")", "(" + code + r")\s+(?:is\s+)?(?:your\s+)?" + marker):
        candidates.extend(re.findall(pattern, content, re.I))
    if re.search(marker, subject, re.I):
        candidates.extend(re.findall(r"(?m)^\s*(" + code + r")\s*$", content))
        candidates.extend(re.findall(r"\bcode(?:\s+is)?[\s:]+(" + code + ")", content, re.I))
    candidates = {value.replace(" ", "").replace("-", "") for value in candidates if any(char.isdigit() for char in value)}
    return next(iter(candidates)) if len(candidates) == 1 else None


def gmail_metadata_from_payload(payload, fallback_id):
    message_headers = payload.get("payload", {}).get("headers", [])
    label_ids = set(payload.get("labelIds", []))
    sender = gmail_header(message_headers, "From")
    metadata = {
        "id": payload.get("id", fallback_id),
        "sender": gmail_sender(sender),
        "email": gmail_sender_email(sender),
        "subject": gmail_header(message_headers, "Subject") or "(No subject)",
        "reply_to": gmail_header(message_headers, "Reply-To"),
        "to": gmail_header(message_headers, "To"),
        "message_id": gmail_header(message_headers, "Message-ID"),
        "references": gmail_header(message_headers, "References"),
        "in_reply_to": gmail_header(message_headers, "In-Reply-To"),
        "thread_id": payload.get("threadId", ""),
        "preview": payload.get("snippet", ""),
        "time": gmail_message_time(gmail_header(message_headers, "Date")),
        "date": gmail_message_full_time(gmail_header(message_headers, "Date")),
        "internal_date": int(payload.get("internalDate", 0) or 0),
        "unread": "UNREAD" in label_ids,
        "starred": "STARRED" in label_ids,
        "label_ids": sorted(label_ids),
        "category": "social" if "CATEGORY_SOCIAL" in label_ids else (
            "updates" if "CATEGORY_UPDATES" in label_ids else "primary"
        ),
    }
    return {**metadata, **email_reply_info(metadata), "otp_code": extract_otp_code(metadata['subject'], metadata['preview'])}


def load_cached_gmail_messages(user):
    """Return the last known inbox when Gmail cannot be reached."""
    rows = get_db().execute(
        "SELECT metadata FROM gmail_cache WHERE user_id = ? AND metadata IS NOT NULL",
        (user["id"],),
    ).fetchall()
    messages = []
    for row in rows:
        try:
            metadata = json.loads(row["metadata"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(metadata, dict):
            messages.append(metadata)
    messages.sort(key=lambda message: message.get("internal_date", 0), reverse=True)
    return messages


GMAIL_LIST_TTL = 5 * 60
def _fetch_gmail_detail(headers, message_id):
    detail = google_requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
        headers=headers,
        params=[
            ("userId", "me"),
            ("format", "metadata"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "Subject"),
            ("metadataHeaders", "Date"),
            ("metadataHeaders", "Reply-To"),
            ("metadataHeaders", "To"),
            ("metadataHeaders", "Message-ID"),
            ("metadataHeaders", "References"),
            ("metadataHeaders", "In-Reply-To"),
        ],
        timeout=(5, 15),
    )
    detail.raise_for_status()
    return gmail_metadata_from_payload(detail.json(), message_id)


def fetch_gmail_message(user, message_id, *, for_reply=False):
    """Fetch and decode one complete Gmail message for the detail view."""
    account = active_email_account(user)
    raw_id = gmail_raw_message_id(account, message_id)
    metadata = gmail_cache_get(user["id"], message_id)
    body = gmail_cache_get(user["id"], message_id, body=True)
    if metadata is not None and body is not None and not (for_reply and "thread_id" not in metadata):
        return {**metadata, "date": gmail_message_date(metadata), "body": body}

    access_token = get_gmail_access_token(user)
    if not access_token:
        return None
    response = google_requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{raw_id}",
        headers={"Authorization": "Bearer " + access_token},
        params={"userId": "me", "format": "full"},
        timeout=(5, 20),
    )
    response.raise_for_status()
    payload = response.json()
    metadata = gmail_metadata_from_payload(payload, message_id)
    metadata['id'] = message_id
    body = decode_gmail_body(payload.get("payload", {}))
    gmail_cache_put(user["id"], message_id, metadata=metadata, body=body)
    return {**metadata, "date": gmail_message_date(metadata), "body": body}


def add_reply_headers(email, original):
    """Copy only well-formed message IDs from the received email into the reply."""
    pattern = r"<[^<>\s\x00-\x1f\x7f]+@[^<>\s\x00-\x1f\x7f]+>"
    parent_ids = re.findall(pattern, original.get("message_id", ""))
    if parent_ids:
        email["In-Reply-To"] = parent_ids[0]
        references = re.findall(pattern, original.get("references", ""))
        email["References"] = " ".join(dict.fromkeys([*references, parent_ids[0]]))


NO_REPLY_ADDRESS_RE = re.compile(r"(?:^|[._+\-])(?:no[._\-]*reply|do[._\-]*not[._\-]*reply)(?=$|[._+\-]|\d)", re.I)


def email_reply_info(message, account=None):
    """Recognise explicit no-reply addresses, allowing a usable Reply-To override."""
    address = message.get("reply_to") or message.get("email", "")
    if account and not message.get("reply_to") and normalize_email(parseaddr(address)[1]) == normalize_email(account["email"]):
        address = message.get("to", "")
    addresses = [normalize_email(email) for _, email in getaddresses([address]) if valid_email(email)]
    target = next((email for email in addresses if not NO_REPLY_ADDRESS_RE.search(email.partition('@')[0])), "")
    return {"reply_address": target, "can_reply": bool(target), "is_no_reply": bool(addresses) and not target}


def reply_address(message, account):
    return email_reply_info(message, account)["reply_address"]


def send_gmail_message(user, recipient, subject, body, *, reply=None):
    access_token = get_gmail_access_token(user)
    if not access_token:
        raise RuntimeError("Google sign-in must be re-authorized before sending email.")
    email = EmailMessage()
    email["To"] = recipient
    email["Subject"] = subject or "(No subject)"
    email["From"] = active_email_account(user)["email"]
    if reply:
        add_reply_headers(email, reply)
    email.set_content(body)
    raw = base64.urlsafe_b64encode(email.as_bytes()).decode().rstrip("=")
    payload = {"raw": raw}
    if reply and reply.get("thread_id"):
        payload["threadId"] = reply["thread_id"]
    response = google_requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    response.raise_for_status()


TELEGRAM_PHONE_RE = re.compile(r"^\+?[0-9]{6,20}$")
TELEGRAM_API_HASH_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_telegram_locks = {}
_telegram_locks_guard = threading.Lock()


def get_integration(user_id, provider):
    row = get_db().execute(
        "SELECT config FROM integrations WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    ).fetchone()
    if row is None:
        return None
    try:
        config = json.loads(row["config"])
    except (TypeError, json.JSONDecodeError):
        return None
    return config if isinstance(config, dict) else None


def save_integration(user_id, provider, config):
    get_db().execute(
        """INSERT INTO integrations (user_id, provider, config, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, provider) DO UPDATE SET
               config = excluded.config,
               updated_at = excluded.updated_at""",
        (user_id, provider, json.dumps(config), time.time()),
    )
    get_db().commit()


def delete_integration(user_id, provider):
    get_db().execute(
        "DELETE FROM integrations WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    get_db().commit()


def _telegram_lock(user_id):
    with _telegram_locks_guard:
        return _telegram_locks.setdefault(user_id, threading.Lock())


def telegram_available():
    return TELETHON_AVAILABLE and TelegramClient is not None


def _telegram_client(config, session=None):
    if not telegram_available():
        raise RuntimeError(
            "Telegram account support is not installed. Run pip install telethon."
        )
    session_text = config.get("session", "") if session is None else session
    return TelegramClient(
        StringSession(session_text),
        int(config["api_id"]),
        config["api_hash"],
        flood_sleep_threshold=0,
    )


def _telegram_account(me):
    name = " ".join(
        part for part in (getattr(me, "first_name", ""), getattr(me, "last_name", "")) if part
    )
    return {
        "id": getattr(me, "id", None),
        "name": name or getattr(me, "username", "") or "Telegram account",
        "username": getattr(me, "username", "") or "",
        "phone": getattr(me, "phone", "") or "",
    }


def telegram_error_text(error):
    if TELETHON_AVAILABLE:
        if isinstance(error, FloodWaitError):
            return f"Telegram asked to wait {error.seconds} seconds before trying again."
        if isinstance(error, PhoneCodeInvalidError):
            return "That login code is not correct. Check Telegram and try again."
        if isinstance(error, PhoneCodeExpiredError):
            return "That login code has expired. Start over to request a new code."
        if isinstance(error, PasswordHashInvalidError):
            return "That two-step verification password is not correct."
        if isinstance(error, SessionPasswordNeededError):
            return "This account uses two-step verification. Enter your password to finish signing in."
        if isinstance(error, ApiIdInvalidError):
            return "The API ID or API hash is not valid. Copy both from my.telegram.org."
        if isinstance(error, PhoneNumberInvalidError):
            return "Enter the phone number in international format, for example +233201234567."
    return str(error) or type(error).__name__


def telegram_send_code(user, api_id, api_hash, phone):
    config = {"api_id": api_id, "api_hash": api_hash, "phone": phone, "stage": "code"}

    async def run():
        client = _telegram_client(config, session="")
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            return sent.phone_code_hash, client.session.save()
        finally:
            await client.disconnect()

    with _telegram_lock(user["id"]):
        phone_code_hash, session_text = asyncio.run(run())
    config.update(phone_code_hash=phone_code_hash, session=session_text)
    save_integration(user["id"], "telegram", config)
    return config


def telegram_verify(user, value, mode):
    config = get_integration(user["id"], "telegram")
    if config is None or config.get("stage") not in {"code", "password"}:
        raise RuntimeError("Start Telegram sign-in again.")
    expected = "password" if mode == "password" else "code"
    if config.get("stage") != expected:
        raise RuntimeError("Finish the current Telegram sign-in step first.")

    async def run():
        client = _telegram_client(config)
        await client.connect()
        try:
            if mode == "password":
                await client.sign_in(password=value)
            else:
                await client.sign_in(
                    phone=config["phone"],
                    code=value,
                    phone_code_hash=config.get("phone_code_hash"),
                )
            me = await client.get_me()
            return {
                "stage": "connected",
                "session": client.session.save(),
                "account": _telegram_account(me),
            }
        except SessionPasswordNeededError:
            return {"stage": "password", "session": client.session.save()}
        finally:
            await client.disconnect()

    with _telegram_lock(user["id"]):
        update = asyncio.run(run())
    config.update(update)
    config.pop("phone_code_hash", None)
    save_integration(user["id"], "telegram", config)
    return config


def _telegram_run(config, user_id, operation, *, timeout=20):
    async def run():
        client = _telegram_client(config)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError("This Telegram session is no longer signed in. Connect your account again.")
            return await operation(client)
        finally:
            await client.disconnect()

    lock = _telegram_lock(user_id)
    if not lock.acquire(timeout=5):
        raise RuntimeError("Telegram is busy. Try loading messages again.")
    try:
        return asyncio.run(asyncio.wait_for(run(), timeout=timeout))
    finally:
        lock.release()


def telegram_snapshot(config, user_id, limit=8):
    async def snapshot(client):
        me = await client.get_me()
        dialogs = await client.get_dialogs(limit=limit)
        messages = []
        for dialog in dialogs:
            message = dialog.message
            media = telegram_message_media(message, str(dialog.id)) if message else None
            forum = bool(getattr(dialog.entity, 'forum', False))
            messages.append({
                'id':message.id if message else None, 'chat_id':str(dialog.id),
                'sender':dialog.name or 'Telegram', 'text':(message.message or ('' if media else '(Media or service message)')) if message else 'No messages yet.',
                'media':media,
                'time':message.date.astimezone().strftime('%b %d, %H:%M') if message else '',
                'kind':'forum' if forum else 'group' if dialog.is_group else 'channel' if dialog.is_channel else 'private',
                'unread':dialog.unread_count,
            })
        return _telegram_account(me), messages
    return _telegram_run(config, user_id, snapshot)


async def _telegram_dialog(client, chat_id):
    # StringSession does not persist entity access hashes; resolve from our own dialogs.
    dialogs = await client.get_dialogs(limit=50)
    dialog = next((item for item in dialogs if str(item.id) == chat_id), None)
    if dialog is None:
        raise ValueError('Choose a conversation from your 50 most recent Telegram chats.')
    return dialog


def _telegram_can_send(dialog):
    entity = dialog.entity
    admin = getattr(entity, 'admin_rights', None)
    if getattr(entity, 'broadcast', False):
        return bool(getattr(entity, 'creator', False) or getattr(admin, 'post_messages', False))
    if getattr(entity, 'creator', False) or admin:
        return True
    for rights in (getattr(entity, 'banned_rights', None), getattr(entity, 'default_banned_rights', None)):
        if rights and (getattr(rights, 'send_messages', False) or getattr(rights, 'send_plain', False)):
            return False
    return True


TELEGRAM_MEDIA_LIMIT = 64 * 1024 * 1024
TELEGRAM_MEDIA_TYPES = {'image/jpeg': 'photo', 'image/png': 'photo', 'image/webp': 'photo',
    'image/gif': 'photo', 'video/mp4': 'video', 'video/webm': 'video', 'video/ogg': 'video'}


def telegram_photo_size(photo):
    return max((size for size in photo.sizes if isinstance(size, (telegram_types.PhotoSize,
        telegram_types.PhotoSizeProgressive, telegram_types.PhotoCachedSize, telegram_types.PhotoStrippedSize))),
        key=lambda size: getattr(size, 'size', None) or max(getattr(size, 'sizes', []) or [len(getattr(size, 'bytes', b''))]),
        default=None)


def telegram_message_media(message, chat_id):
    media = getattr(message, 'media', None)
    filename = 'telegram-' + str(message.id)
    if isinstance(media, telegram_types.MessageMediaPhoto) and isinstance(media.photo, telegram_types.Photo):
        photo = telegram_photo_size(media.photo)
        if photo is None: return None
        size = getattr(photo, 'size', None) or max(getattr(photo, 'sizes', []) or [len(getattr(photo, 'bytes', b''))])
        mime = 'image/jpeg'
        filename += '.jpg'
    elif isinstance(media, telegram_types.MessageMediaDocument) and isinstance(media.document, telegram_types.Document):
        size, mime = media.document.size, media.document.mime_type
        filename = next((attribute.file_name for attribute in media.document.attributes if isinstance(attribute, telegram_types.DocumentAttributeFilename)), filename + (mimetypes.guess_extension(mime) or '.bin'))
    else:
        return None
    kind = TELEGRAM_MEDIA_TYPES.get(mime, 'file')
    return {'kind': kind, 'mime_type': mime if kind != 'file' else 'application/octet-stream', 'size': size,
        'name':secure_filename(filename) or 'attachment.bin',
        'url': url_for('telegram_media_route', chat_id=chat_id, message_id=message.id),
        'available': size <= TELEGRAM_MEDIA_LIMIT}


def _telegram_in_topic(message, topic_id):
    if not topic_id: return True
    if isinstance(getattr(message, 'action', None), telegram_types.MessageActionTopicCreate):
        return message.id == int(topic_id)
    reply = getattr(message, 'reply_to', None)
    root = getattr(reply, 'reply_to_top_id', None) or (getattr(reply, 'reply_to_msg_id', None) if getattr(reply, 'forum_topic', False) else None)
    return root in (None, 1) if topic_id == '1' else root == int(topic_id) or message.id == int(topic_id)


def _telegram_can_pin(dialog):
    entity = dialog.entity
    admin = getattr(entity, 'admin_rights', None)
    if getattr(entity, 'creator', False) or getattr(admin, 'pin_messages', False): return True
    if getattr(entity, 'broadcast', False): return False
    return not any(getattr(rights, 'pin_messages', False) for rights in
        (getattr(entity, 'banned_rights', None), getattr(entity, 'default_banned_rights', None)))


def _telegram_message_data(message, dialog):
    sender = getattr(message, 'sender', None)
    name = getattr(sender, 'title', None) or (_telegram_account(sender)['name'] if sender else 'Telegram')
    media = telegram_message_media(message, str(dialog.id))
    own = bool(message.out) and not getattr(message, 'action', None)
    link = None
    if getattr(dialog.entity, 'username', None): link = f'https://t.me/{dialog.entity.username}/{message.id}'
    elif str(dialog.id).startswith('-100'): link = f'https://t.me/c/{str(dialog.id)[4:]}/{message.id}'
    reactions = [{'emoji':item.reaction.emoticon, 'count':item.count, 'chosen':getattr(item, 'chosen_order', None) is not None}
        for item in getattr(getattr(message, 'reactions', None), 'results', []) if isinstance(item.reaction, telegram_types.ReactionEmoji)]
    return {'id':str(message.id), 'sender':'You' if message.out else name, 'outgoing':bool(message.out),
        'text':message.message or ('' if media else '(Media or service message)'), 'media':media,
        'time':message.date.astimezone().strftime('%b %d, %H:%M'), 'edited':bool(getattr(message, 'edit_date', None)),
        'pinned':bool(getattr(message, 'pinned', False)), 'reactions':reactions, 'link':link,
        'can_edit':own and bool(message.message or getattr(message, 'media', None)),
        'edit_limit':1024 if getattr(message, 'media', None) else 4096,
        'can_delete':own, 'can_delete_for_me':own and not dialog.is_channel,
        'can_forward':own and not (getattr(dialog.entity, 'noforwards', False) or getattr(message, 'noforwards', False)),
        'can_pin':own and _telegram_can_pin(dialog), 'can_react':own}


async def _telegram_message(client, dialog, message_id, topic_id=None):
    message = await client.get_messages(dialog.input_entity, ids=message_id)
    if not message or message.id != message_id or str(getattr(message, 'chat_id', '')) != str(dialog.id) or not _telegram_in_topic(message, topic_id):
        raise ValueError('This message is no longer available in this conversation or topic.')
    return message


def telegram_message_action(config, user_id, chat_id, message_id, action, *, text='', topic_id=None,
                            original=None, destination=None, destination_topic=None, request_id='', emoji='', revoke=True):
    async def change(client):
        dialog = await _telegram_dialog(client, chat_id)
        message = await _telegram_message(client, dialog, message_id, topic_id)
        data = _telegram_message_data(message, dialog)
        if not data.get('can_' + ('react' if action == 'reaction' else 'pin' if action == 'unpin' else action)):
            raise ValueError('This action is unavailable for this message or your Telegram permissions.')
        try:
            if action == 'edit':
                if len(text.encode('utf-16-le')) // 2 > data['edit_limit'] or (not text.strip() and not getattr(message, 'media', None)):
                    raise ValueError(f"Enter a message of up to {data['edit_limit']:,} characters.")
                if message.message != text:
                    if original is not None and (message.message or '') != original:
                        raise ValueError('This message changed since you opened it. Cancel and refresh before editing again.')
                    await client.edit_message(dialog.input_entity, message_id, text, parse_mode=None, link_preview=False)
            elif action == 'delete':
                if not revoke and not data['can_delete_for_me']:
                    raise ValueError('Messages in this conversation can only be deleted for everyone.')
                await client.delete_messages(dialog.input_entity, [message_id], revoke=revoke)
                return {'deleted':True, 'id':str(message_id)}
            elif action == 'forward':
                target = await _telegram_dialog(client, destination)
                if not _telegram_can_send(target): raise ValueError('The destination is read-only.')
                if getattr(target.entity, 'forum', False):
                    if not destination_topic: raise ValueError('Choose a destination topic for this forum group.')
                    topics = await client(telegram_functions.messages.GetForumTopicsByIDRequest(peer=target.input_entity, topics=[int(destination_topic)]))
                    topic = next((item for item in topics.topics if isinstance(item, telegram_types.ForumTopic) and str(item.id) == destination_topic), None)
                    if not topic or topic.closed or topic.hidden: raise ValueError('The destination topic is unavailable or read-only.')
                elif destination_topic: raise ValueError('The destination has topics disabled.')
                identity = '\0'.join((str(user_id), config['session'], chat_id, str(message_id), destination, destination_topic or '', request_id))
                random_id = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], 'big') & ((1 << 63) - 1)
                await client(telegram_functions.messages.ForwardMessagesRequest(from_peer=dialog.input_entity, id=[message_id],
                    to_peer=target.input_entity, random_id=[random_id], top_msg_id=int(destination_topic) if destination_topic and destination_topic != '1' else None))
                return {'forwarded':True}
            elif action in {'pin', 'unpin'}:
                await client(telegram_functions.messages.UpdatePinnedMessageRequest(peer=dialog.input_entity, id=message_id, silent=True, unpin=action == 'unpin'))
            elif action == 'reaction':
                await client(telegram_functions.messages.SendReactionRequest(peer=dialog.input_entity, msg_id=message_id,
                    reaction=[telegram_types.ReactionEmoji(emoji)] if emoji else []))
        except telegram_errors.MessageNotModifiedError:
            pass
        except telegram_errors.MessageEditTimeExpiredError:
            raise ValueError('Telegram’s time limit for editing this message has passed.') from None
        except telegram_errors.MessageAuthorRequiredError:
            raise ValueError('You can only edit your own Telegram messages.') from None
        except telegram_errors.ChatAdminRequiredError:
            raise ValueError('Telegram requires administrator permission for this action.') from None
        except telegram_errors.ChatForwardsRestrictedError:
            raise ValueError('Forwarding is disabled in this conversation.') from None
        except telegram_errors.ReactionInvalidError:
            raise ValueError('This reaction is not available in this conversation. Try another emoji.') from None
        updated = await _telegram_message(client, dialog, message_id, topic_id)
        return {'message':_telegram_message_data(updated, dialog)}
    return _telegram_run(config, user_id, change)


def telegram_chat(config, user_id, chat_id, *, topic_id=None, topic_query='', before=0, after=0, text=None, request_id=None, reply_id=None, known_ids=()):
    async def conversation(client):
        dialog = await _telegram_dialog(client, chat_id)
        forum = bool(getattr(dialog.entity, 'forum', False))
        topics = []
        if forum:
            result = await client(telegram_functions.messages.GetForumTopicsRequest(peer=dialog.input_entity, offset_date=None, offset_id=0, offset_topic=0, limit=100, q=topic_query or None))
            topics = [{'id':str(topic.id), 'title':topic.title, 'closed':bool(topic.closed), 'hidden':bool(topic.hidden)} for topic in result.topics if isinstance(topic, telegram_types.ForumTopic)]
            if topic_id and not any(topic['id'] == topic_id for topic in topics):
                result = await client(telegram_functions.messages.GetForumTopicsByIDRequest(peer=dialog.input_entity, topics=[int(topic_id)]))
                topics.extend({'id':str(topic.id), 'title':topic.title, 'closed':bool(topic.closed), 'hidden':bool(topic.hidden)} for topic in result.topics if isinstance(topic, telegram_types.ForumTopic) and str(topic.id) == topic_id)
        if topic_id is not None and not forum:
            raise ValueError('This group has topics disabled.')
        topic = next((item for item in topics if item['id'] == topic_id), None)
        if topic_id is not None and topic is None:
            raise ValueError('This topic is unavailable. Refresh the topic list.')
        can_send = _telegram_can_send(dialog) and not (topic and (topic['closed'] or topic['hidden']))
        if text is not None:
            if forum and topic is None:
                raise ValueError('Choose a topic before sending a message.')
            if not can_send:
                raise ValueError('This conversation or topic is read-only for your account.')
            if reply_id: await _telegram_message(client, dialog, reply_id, topic_id)
            identity = '\0'.join((str(user_id), config['session'], chat_id, topic_id or '', str(reply_id or ''), request_id))
            random_id = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], 'big') & ((1 << 63) - 1)
            reply = telegram_types.InputReplyToMessage(reply_to_msg_id=reply_id or int(topic_id), top_msg_id=int(topic_id) if reply_id and topic_id and topic_id != '1' else None) if reply_id or (topic_id and topic_id != '1') else None
            # Telegram deduplicates retries with the same random_id after uncertain sends.
            await client(telegram_functions.messages.SendMessageRequest(peer=dialog.input_entity, message=text, random_id=random_id, reply_to=reply, no_webpage=True))
            return {'sent':True}
        messages = []
        raw = []
        if not forum or topic:
            kwargs = {'reply_to':int(topic_id)} if topic_id and topic_id != '1' else {}
            if after: kwargs.update(min_id=after, reverse=True)
            raw = await client.get_messages(dialog.input_entity, limit=50, offset_id=before, **kwargs)
            for message in raw if after else reversed(raw):
                if topic_id == '1':
                    if isinstance(getattr(message, 'action', None), telegram_types.MessageActionTopicCreate) and message.id != 1:
                        continue
                    reply = getattr(message, 'reply_to', None)
                    root = getattr(reply, 'reply_to_top_id', None) or (getattr(reply, 'reply_to_msg_id', None) if getattr(reply, 'forum_topic', False) else None)
                    if root not in (None, 1):
                        continue
                messages.append(_telegram_message_data(message, dialog))
        updated = []
        if known_ids:
            current = await client.get_messages(dialog.input_entity, ids=list(known_ids))
            updated = [_telegram_message_data(message, dialog) for message in current if message and str(getattr(message, 'chat_id', '')) == chat_id and _telegram_in_topic(message, topic_id)]
        return {'chat_id':chat_id, 'name':dialog.name, 'forum':forum, 'topics':topics, 'topic_id':topic_id, 'can_send':can_send and (not forum or topic is not None), 'messages':messages,
            'updated_messages':updated, 'deleted_ids':[str(identifier) for identifier in known_ids if str(identifier) not in {message['id'] for message in updated}],
            'next_before':str(raw[-1].id) if len(raw) == 50 and not after else None, 'latest_seen':str(raw[-1 if after else 0].id) if raw else None, 'has_more_new':bool(after and len(raw) == 50)}
    return _telegram_run(config, user_id, conversation)


def telegram_photo(config, user_id, chat_id):
    async def photo(client):
        entity = 'me' if chat_id == 'me' else (await _telegram_dialog(client, chat_id)).entity
        return await client.download_profile_photo(entity, file=bytes, download_big=False)
    return _telegram_run(config, user_id, photo)


def telegram_message_download(config, user_id, chat_id, message_id):
    async def download(client):
        dialog = await _telegram_dialog(client, chat_id)
        message = await client.get_messages(dialog.input_entity, ids=message_id)
        if not message or message.id != message_id or str(getattr(message, 'chat_id', '')) != chat_id:
            raise ValueError('This media is no longer available in this conversation.')
        media = telegram_message_media(message, chat_id)
        if not media: raise ValueError('This message does not contain a downloadable file.')
        if not media['available']: raise ValueError('Open Telegram for media larger than 64 MB.')
        # Telethon accepts progressive photo sizes by key, but not by object.
        kwargs = {'thumb': telegram_photo_size(message.media.photo).type} if isinstance(message.media, telegram_types.MessageMediaPhoto) else {}
        content = await client.download_media(message, file=bytes, **kwargs)
        if not isinstance(content, bytes) or not content or len(content) > TELEGRAM_MEDIA_LIMIT:
            raise ValueError('This media could not be loaded.')
        return content, media['mime_type'], media['name']
    return _telegram_run(config, user_id, download, timeout=60)


def telegram_send_test(config, user_id):
    async def run():
        client = _telegram_client(config)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise RuntimeError(
                    "This Telegram session is no longer signed in. Connect your account again."
                )
            await client.send_message(
                "me",
                "CentroMail connection test: your Telegram account is connected.",
            )
        finally:
            await client.disconnect()

    with _telegram_lock(user_id):
        asyncio.run(run())


def telegram_disconnect(config, user_id):
    if not telegram_available() or not config or not config.get("session"):
        return

    async def run():
        client = _telegram_client(config)
        await client.connect()
        try:
            if await client.is_user_authorized():
                await client.log_out()
        finally:
            await client.disconnect()

    try:
        with _telegram_lock(user_id):
            asyncio.run(run())
    except Exception as error:  # The local connection is removed regardless.
        app.logger.warning(
            "Telegram logout failed for user id=%s: %s", user_id, telegram_error_text(error)
        )


WHATSAPP_API_VERSION = "v22.0"
WHATSAPP_GRAPH = "https://graph.facebook.com/{version}/{phone_number_id}"
WHATSAPP_FIELDS = "verified_name,display_phone_number,quality_rating"


def whatsapp_response_error(response):
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    message = error.get("message") if isinstance(error, dict) else None
    return message or f"WhatsApp returned HTTP {response.status_code}."


def whatsapp_request(config, method, path="", params=None, payload=None):
    token = config.get("access_token", "")
    if not token:
        raise RuntimeError("Connect WhatsApp again to refresh the access token.")
    response = requests.request(
        method,
        WHATSAPP_GRAPH.format(
            version=WHATSAPP_API_VERSION,
            phone_number_id=config["phone_number_id"],
        )
        + path,
        headers={"Authorization": "Bearer " + token},
        params=params,
        json=payload,
        timeout=(5, 20),
    )
    if response.status_code >= 400:
        raise RuntimeError(whatsapp_response_error(response))
    return response.json() if response.content else {}


def connect_whatsapp(user, phone_number_id, access_token, verify_token):
    config = {
        "phone_number_id": phone_number_id,
        "access_token": access_token,
        "verify_token": verify_token or secrets.token_urlsafe(24),
    }
    profile = whatsapp_request(config, "GET", params={"fields": WHATSAPP_FIELDS})
    config.update(
        {
            "verified_name": profile.get("verified_name", ""),
            "display_phone_number": profile.get("display_phone_number", ""),
            "quality_rating": profile.get("quality_rating", ""),
        }
    )
    save_integration(user["id"], "whatsapp", config)
    return config


def whatsapp_send_message(config, recipient, text):
    return whatsapp_request(
        config,
        "POST",
        "/messages",
        payload={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        },
    )


def store_whatsapp_message(user_id, message):
    text = message.get("text") or {}
    body = text.get("body") if isinstance(text, dict) else None
    if not body:
        body = message.get("caption") or "(Non-text WhatsApp message)"
    message_id = str(message.get("id") or f"{time.time():.6f}")
    sender = str(message.get("from") or "WhatsApp")
    try:
        received_at = float(message.get("timestamp") or time.time())
    except (TypeError, ValueError):
        received_at = time.time()
    get_db().execute(
        """INSERT INTO whatsapp_messages (user_id, message_id, sender, body, received_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id, message_id) DO NOTHING""",
        (user_id, message_id, sender, body[:2000], received_at),
    )
    get_db().commit()


def whatsapp_recent_messages(user_id, limit=8):
    rows = get_db().execute(
        """SELECT sender, body, received_at FROM whatsapp_messages
           WHERE user_id = ? ORDER BY received_at DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [
        {
            "sender": row["sender"],
            "text": row["body"],
            "time": datetime.fromtimestamp(row["received_at"], timezone.utc)
            .astimezone()
            .strftime("%b %d, %H:%M"),
        }
        for row in rows
    ]


def find_whatsapp_integration(phone_number_id=None, verify_token=None):
    rows = get_db().execute(
        "SELECT user_id, config FROM integrations WHERE provider = 'whatsapp'"
    ).fetchall()
    matched = None
    for row in rows:
        try:
            config = json.loads(row["config"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(config, dict):
            continue
        if phone_number_id and config.get("phone_number_id") == phone_number_id:
            matched = (row["user_id"], config)
            if phone_number_id:
                break
        if verify_token and secrets.compare_digest(
            str(config.get("verify_token", "")), str(verify_token)
        ):
            matched = (row["user_id"], config)
            break
    return matched if matched is not None else (None, None)


DISCORD_API = "https://discord.com/api/v10"
DISCORD_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{20,200}$")


def discord_response_error(response):
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    message = payload.get("message") if isinstance(payload, dict) else None
    if response.status_code == 401:
        return "The Discord bot token is not valid."
    if response.status_code == 403:
        return "The bot does not have permission to view or post in that channel."
    if response.status_code == 404:
        return "Discord could not find that channel. Check the channel ID."
    if response.status_code == 429:
        retry = payload.get("retry_after") if isinstance(payload, dict) else None
        return f"Discord is rate limiting requests. Try again in {retry or 'a few'} seconds."
    return message or f"Discord returned HTTP {response.status_code}."


def discord_request(config, method, path, params=None, payload=None):
    token = config.get("bot_token", "")
    if not token:
        raise RuntimeError("Connect Discord again to refresh the bot token.")
    response = requests.request(
        method,
        DISCORD_API + path,
        headers={
            "Authorization": "Bot " + token,
            "Content-Type": "application/json",
        },
        params=params,
        json=payload,
        timeout=(5, 20),
    )
    if response.status_code >= 400:
        raise RuntimeError(discord_response_error(response))
    return response.json() if response.content else {}


def connect_discord(user, bot_token, channel_id):
    config = {"bot_token": bot_token, "channel_id": channel_id}
    bot = discord_request(config, "GET", "/users/@me")
    channel = discord_request(config, "GET", f"/channels/{channel_id}")
    guild = {}
    if channel.get("guild_id"):
        try:
            guild = discord_request(config, "GET", f"/guilds/{channel['guild_id']}")
        except (requests.RequestException, RuntimeError):
            guild = {}
    config.update(
        {
            "bot_name": bot.get("global_name") or bot.get("username") or "Discord bot",
            "bot_username": bot.get("username", ""),
            "bot_id": bot.get("id", ""),
            "channel_name": channel.get("name", "") or channel_id,
            "guild_name": guild.get("name", ""),
        }
    )
    save_integration(user["id"], "discord", config)
    return config


def discord_recent_messages(config, limit=8):
    messages = discord_request(
        config,
        "GET",
        f"/channels/{config['channel_id']}/messages",
        params={"limit": limit},
    )
    items = []
    for message in reversed(messages or []):
        author = message.get("author", {}) or {}
        name = author.get("global_name") or author.get("username") or "Discord"
        content = message.get("content") or "(No text content)"
        timestamp = message.get("timestamp") or ""
        try:
            when = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone()
            label = when.strftime("%b %d, %H:%M")
        except (TypeError, ValueError):
            label = ""
        items.append({"id": message.get("id"), "sender": name, "text": content, "time": label})
    return items


def discord_send_message(config, text):
    return discord_request(
        config,
        "POST",
        f"/channels/{config['channel_id']}/messages",
        payload={"content": text[:2000]},
    )


SOCIAL_TIMEOUT = (5, 20)


def social_field(name, label, field_type="text", placeholder="", required=True):
    return {
        "name": name,
        "label": label,
        "type": field_type,
        "placeholder": placeholder,
        "required": required,
    }


SOCIAL_PROVIDERS = [
    {
        "key": "x",
        "name": "X",
        "mark": "X",
        "subtitle": "Posts, replies and profile",
        "help": "Create an app at developer.x.com, then use an OAuth 2.0 user access token with tweet.read and tweet.write.",
        "fields": [social_field("access_token", "OAuth 2.0 access token", "password", "Paste your X access token")],
        "test": True,
        "test_label": "Post test tweet",
        "test_placeholder": "Hello from CentroMail",
        "max_length": 280,
    },
    {
        "key": "linkedin",
        "name": "LinkedIn",
        "mark": "in",
        "subtitle": "Member posts and profile",
        "help": "Use a LinkedIn OAuth 2.0 access token with openid, profile and w_member_social scopes.",
        "fields": [social_field("access_token", "Access token", "password", "Paste your LinkedIn token")],
        "test": True,
        "test_label": "Post test update",
        "test_placeholder": "Hello from CentroMail",
        "max_length": 3000,
    },
    {
        "key": "reddit",
        "name": "Reddit",
        "mark": "r",
        "subtitle": "Profile, subreddits and posts",
        "help": "Create a Reddit script app and paste an OAuth access token with identity and read scopes.",
        "fields": [social_field("access_token", "OAuth access token", "password", "Paste your Reddit token")],
        "test": False,
        "note": "Posting needs a subreddit and title, so CentroMail validates the connection here.",
    },
    {
        "key": "mastodon",
        "name": "Mastodon",
        "mark": "M",
        "subtitle": "Posts and federated profile",
        "help": "In Mastodon open Preferences, Development, New application, and copy the access token. Enter the instance domain.",
        "fields": [
            social_field("instance", "Instance", "text", "mastodon.social"),
            social_field("access_token", "Access token", "password", "Paste your Mastodon token"),
        ],
        "test": True,
        "test_label": "Post test status",
        "test_placeholder": "Hello from CentroMail",
        "max_length": 500,
    },
    {
        "key": "bluesky",
        "name": "Bluesky",
        "mark": "B",
        "subtitle": "Posts and AT Protocol profile",
        "help": "Use your handle and an App Password from bsky.app Settings, Privacy and security, App passwords.",
        "fields": [
            social_field("handle", "Handle", "text", "you.bsky.social"),
            social_field("app_password", "App password", "password", "xxxx-xxxx-xxxx-xxxx"),
        ],
        "test": True,
        "test_label": "Post test skeet",
        "test_placeholder": "Hello from CentroMail",
        "max_length": 300,
    },
    {
        "key": "tiktok",
        "name": "TikTok",
        "mark": "Tt",
        "subtitle": "Profile and creator info",
        "help": "Create a TikTok developer app and paste an access token with user.info.basic.",
        "fields": [social_field("access_token", "Access token", "password", "Paste your TikTok token")],
        "test": False,
        "note": "Video publishing needs a hosted video file, so CentroMail validates the connection here.",
    },
    {
        "key": "pinterest",
        "name": "Pinterest",
        "mark": "P",
        "subtitle": "Profile and boards",
        "help": "Create a Pinterest developer app and paste an access token with user_accounts:read.",
        "fields": [social_field("access_token", "Access token", "password", "Paste your Pinterest token")],
        "test": False,
        "note": "Pins require an image URL, so CentroMail validates the connection here.",
    },
    {
        "key": "tumblr",
        "name": "Tumblr",
        "mark": "t",
        "subtitle": "Blogs and posts",
        "help": "Create a Tumblr OAuth app and paste an OAuth 2.0 access token.",
        "fields": [social_field("access_token", "Access token", "password", "Paste your Tumblr token")],
        "test": False,
        "note": "Tumblr posting needs a blog identifier, so CentroMail validates the connection here.",
    },
    {
        "key": "twitch",
        "name": "Twitch",
        "mark": "Tw",
        "subtitle": "Channel and streaming profile",
        "help": "Create a Twitch developer app and paste its client ID plus an OAuth user access token.",
        "fields": [
            social_field("client_id", "Client ID", "text", "Your Twitch client ID"),
            social_field("access_token", "User access token", "password", "Paste your Twitch token"),
        ],
        "test": False,
        "note": "Chat and stream actions need additional bot scopes, so CentroMail validates the connection here.",
    },
    {
        "key": "slack",
        "name": "Slack",
        "mark": "S",
        "subtitle": "Workspace channels and messages",
        "help": "Create a Slack app, install it to your workspace, and paste the bot token plus the target channel ID.",
        "fields": [
            social_field("bot_token", "Bot token", "password", "xoxb-..."),
            social_field("channel_id", "Channel ID", "text", "C0123456789"),
        ],
        "test": True,
        "test_label": "Send test message",
        "test_placeholder": "Hello from CentroMail",
        "max_length": 4000,
    },
]

SOCIAL_PROVIDERS_BY_KEY = {provider["key"]: provider for provider in SOCIAL_PROVIDERS}


def social_error(response):
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if isinstance(payload, dict):
        for key in ("error_description", "message", "detail", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                nested = value.get("message")
                if nested:
                    return nested
    return f"The service returned HTTP {response.status_code}."


def social_request(url, token="", method="GET", params=None, payload=None, headers=None):
    request_headers = dict(headers or {})
    if token:
        request_headers["Authorization"] = "Bearer " + token
    response = requests.request(
        method,
        url,
        headers=request_headers,
        params=params,
        json=payload,
        timeout=SOCIAL_TIMEOUT,
    )
    if response.status_code >= 400:
        raise RuntimeError(social_error(response))
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def mastodon_base_url(instance):
    value = instance.strip()
    parsed = urlparse(value if "://" in value else "https://" + value)
    try:
        port = parsed.port
        hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    except (ValueError, UnicodeError):
        raise RuntimeError("Enter a valid Mastodon instance domain.") from None
    if (parsed.scheme != "https" or not hostname or "." not in hostname
            or parsed.username is not None or parsed.password is not None
            or port not in {None, 443} or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise RuntimeError("Enter an HTTPS Mastodon domain without credentials, paths, or a custom port.")
    return "https://" + hostname


def mastodon_request(base_url, path, token, method="GET", payload=None):
    base_url = mastodon_base_url(base_url)
    hostname = urlparse(base_url).hostname
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
    except OSError as error:
        raise requests.ConnectionError("The Mastodon instance could not be resolved.") from error
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise RuntimeError("Mastodon instances must resolve to public internet addresses.")
    with urllib3.HTTPSConnectionPool(sorted(addresses)[0], port=443,
            server_hostname=hostname, assert_hostname=hostname, ssl_context=ssl.create_default_context()) as pool:
        try:
            response = pool.urlopen(method, path,
                body=json.dumps(payload).encode() if payload is not None else None,
                headers={"Host": hostname, "Authorization": "Bearer " + token, "Content-Type": "application/json"},
                timeout=urllib3.Timeout(connect=5, read=20), redirect=False, retries=False)
        except urllib3.exceptions.HTTPError as error:
            raise requests.ConnectionError("The Mastodon instance could not be reached.") from error
        if 300 <= response.status < 400:
            raise RuntimeError("Mastodon redirects are not accepted. Enter the final instance domain.")
        if response.status >= 400:
            raise RuntimeError(f"Mastodon returned HTTP {response.status}.")
        try:
            data = json.loads(response.data)
        except (ValueError, UnicodeError):
            raise RuntimeError("Mastodon returned an unreadable response.") from None
        if not isinstance(data, dict):
            raise RuntimeError("Mastodon returned an unexpected response.")
        return data


def social_profile(provider, config):
    token = config.get("access_token") or config.get("bot_token") or ""

    if provider == "x":
        data = social_request("https://api.x.com/2/users/me", token)
        user = data.get("data") or {}
        config["account"] = user.get("name") or "X account"
        config["detail"] = f"@{user['username']}" if user.get("username") else ""
    elif provider == "linkedin":
        data = social_request("https://api.linkedin.com/v2/userinfo", token)
        config["account"] = data.get("name") or data.get("email") or "LinkedIn member"
        config["detail"] = data.get("email", "")
        config["member_id"] = data.get("sub", "")
    elif provider == "reddit":
        data = social_request(
            "https://oauth.reddit.com/api/v1/me",
            token,
            headers={"User-Agent": "CentroMail/1.0"},
        )
        config["account"] = "u/" + data.get("name", "reddit")
        config["detail"] = f"{data.get('link_karma', 0)} link karma"
    elif provider == "mastodon":
        base_url = mastodon_base_url(config.get("instance", ""))
        config["instance"] = urlparse(base_url).hostname
        data = mastodon_request(base_url, "/api/v1/accounts/verify_credentials", token)
        config["account"] = "@" + data.get("acct", "mastodon")
        config["detail"] = data.get("display_name", "")
        config["base_url"] = base_url
    elif provider == "bluesky":
        response = requests.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={
                "identifier": config.get("handle", "").lstrip("@"),
                "password": config.get("app_password", ""),
            },
            timeout=SOCIAL_TIMEOUT,
        )
        if response.status_code >= 400:
            raise RuntimeError(social_error(response))
        data = response.json()
        config.update(
            {
                "handle": data.get("handle", config.get("handle", "")),
                "access_token": data.get("accessJwt", ""),
                "refresh_token": data.get("refreshJwt", ""),
                "did": data.get("did", ""),
            }
        )
        config["account"] = "@" + config["handle"]
        config["detail"] = "App password session"
    elif provider == "tiktok":
        data = social_request(
            "https://open.tiktokapis.com/v2/user/info/",
            token,
            params={"fields": "open_id,display_name"},
        )
        user = (data.get("data") or {}).get("user") or {}
        if not user.get('open_id'):
            raise RuntimeError('TikTok could not confirm your profile. Check the token and user.info.basic permission.')
        config["account"] = user.get("display_name") or "TikTok account"
        config["detail"] = "@" + user["username"] if user.get("username") else ""
    elif provider == "pinterest":
        data = social_request("https://api.pinterest.com/v5/user_account", token)
        config["account"] = data.get("username") or "Pinterest account"
        config["detail"] = data.get("account_type", "")
    elif provider == "tumblr":
        data = social_request("https://api.tumblr.com/v2/user/info", token)
        user = (data.get("response") or {}).get("user") or {}
        blogs = user.get("blogs") or []
        config["account"] = user.get("name") or "Tumblr"
        config["detail"] = f"{len(blogs)} blog(s)" if blogs else ""
    elif provider == "twitch":
        data = social_request(
            "https://api.twitch.tv/helix/users",
            token,
            headers={"Client-Id": config.get("client_id", "")},
        )
        user = (data.get("data") or [{}])[0]
        config["account"] = user.get("display_name") or "Twitch channel"
        config["detail"] = "@" + user["login"] if user.get("login") else ""
    elif provider == "slack":
        data = social_request("https://slack.com/api/auth.test", token, method="POST")
        if not data.get("ok"):
            raise RuntimeError(data.get("error", "Slack rejected the bot token."))
        config["account"] = data.get("team") or "Slack workspace"
        config["detail"] = "#" + config.get("channel_id", "")
    else:
        raise RuntimeError("This provider is not supported.")

    return config


def social_publish(provider, config, text):
    token = config.get("access_token") or config.get("bot_token") or ""

    if provider == "x":
        social_request(
            "https://api.x.com/2/tweets",
            token,
            method="POST",
            payload={"text": text[:280]},
        )
    elif provider == "linkedin":
        social_request(
            "https://api.linkedin.com/v2/ugcPosts",
            token,
            method="POST",
            headers={
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            },
            payload={
                "author": "urn:li:person:" + config.get("member_id", ""),
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": text[:3000]},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                },
            },
        )
    elif provider == "mastodon":
        mastodon_request(config.get("base_url", "https://mastodon.social"), "/api/v1/statuses",
            token, method="POST", payload={"status": text[:500]})
    elif provider == "bluesky":
        social_request(
            "https://bsky.social/xrpc/com.atproto.repo.createRecord",
            token,
            method="POST",
            payload={
                "repo": config.get("did", ""),
                "collection": "app.bsky.feed.post",
                "record": {
                    "$type": "app.bsky.feed.post",
                    "text": text[:300],
                    "createdAt": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                },
            },
        )
    elif provider == "slack":
        data = social_request(
            "https://slack.com/api/chat.postMessage",
            token,
            method="POST",
            payload={
                "channel": config.get("channel_id", ""),
                "text": text[:4000],
            },
        )
        if not data.get("ok"):
            raise RuntimeError(data.get("error", "Slack rejected the message."))
    else:
        raise RuntimeError("This provider only supports validating the connection.")


def social_connect(provider, values):
    spec = SOCIAL_PROVIDERS_BY_KEY.get(provider)
    if spec is None:
        raise RuntimeError("Unknown social provider.")
    config = {}
    for field in spec["fields"]:
        value = values.get(field["name"], "").strip()
        if field["name"] == "access_token" and value.lower().startswith("bearer "):
            value = value[7:].strip()
        if field["required"] and not value:
            raise RuntimeError(f"Enter {field['label'].lower()}.")
        if len(value) > 4096:
            raise RuntimeError(f"{field['label']} is too long.")
        config[field["name"]] = value
    config["provider"] = provider
    config["connected_at"] = int(time.time())
    return social_profile(provider, config)


def google_callback_uri():
    return (
        app.config["GOOGLE_REDIRECT_URI"]
        or url_for("google_callback", _external=True)
    )


@app.route('/')
def index():
    return render_template('landing.html')

@app.get('/onboarding')
def onboarding():
    if g.user is not None:
        return redirect(url_for('dashboard'))
    return render_template('login.html', email="", name="", remember=False)


@app.post('/continue')
def continue_flow():
    if g.user is not None:
        return redirect(url_for('dashboard'))
    email = normalize_email(request.form.get('email', ''))
    if not valid_email(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for('login'))
    session["pending_email"] = email
    return redirect(url_for('login' if find_user(email) else 'register'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user is not None:
        return redirect(url_for('dashboard'))
    email = session.get('pending_email', '')
    email_error = ''
    remember = False
    if request.method == 'POST':
        email = normalize_email(request.form.get('email', ''))
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        if not valid_email(email):
            email_error = "Please enter a valid email address."
        elif not password:
            flash("Please enter your password.", "error")
        elif len(password) > 1024:
            flash("Incorrect email or password. Please try again.", "error")
        else:
            user = find_user(email)
            if user is not None and check_password_hash(user["password"], password):
                sign_in(user, remember=remember)
                return redirect(url_for('dashboard'))
            flash("Incorrect email or password. Please try again.", "error")
    return render_auth(email=email, remember=remember, email_error=email_error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if g.user is not None:
        return redirect(url_for('dashboard'))
    email = session.get('pending_email', '')
    email_error = ''
    name = ''
    if request.method == 'POST':
        email = normalize_email(request.form.get('email', ''))
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirmation = request.form.get('confirm_password', '')
        if not name or len(name) > 100:
            flash("Enter a name between 1 and 100 characters.", "error")
        elif not valid_email(email):
            email_error = "Please enter a valid email address."
        elif error := new_password_error(password, email, name):
            flash(error, "error")
        elif password != confirmation:
            flash("Your passwords do not match.", "error")
        elif error := email_address_error(email, check_domain=True):
            email_error = error
        else:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                    (name, email, generate_password_hash(password)),
                )
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                flash("An account with this email already exists. Please log in.", "error")
            else:
                sign_in(find_user(email))
                return redirect(url_for('dashboard'))
    return render_auth(active_panel='signup', email=email, name=name, email_error=email_error)


@app.route('/home')
def home():
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    return render_template(
        'dashboard.html',
        stats=make_stats(load_cached_gmail_messages(g.user)),
        user_email=session.get('user_email'),
    )


@app.get('/privacy')
def privacy():
    return render_template('privacy.html')


@app.get('/terms')
def terms():
    return render_template('terms.html')


@app.post('/account/delete')
def delete_account():
    """Delete the signed-in account and locally stored account data."""
    user_id = g.user["id"]
    db = get_db()
    for table in (
        "gmail_cache", "gmail_sync_state", "gmail_folder_pages", "gmail_mailbox_counts", "gmail_account_counts",
        "whatsapp_messages", "integrations",
    ):
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    session.clear()
    flash("Your CentroMail account and locally stored data were deleted.", "info")
    return redirect(url_for('login'))


INBOX_PAGE_SIZE = 50
MAIL_BATCH_SIZE = 25
GMAIL_FOLDERS = {
    "inbox": {"title": "Inbox", "icon": "inbox", "label": "INBOX"},
    "starred": {"title": "Starred", "icon": "star", "label": "STARRED"},
    "snoozed": {"title": "Snoozed", "icon": "snooze", "query": "in:snoozed"},
    "sent": {"title": "Sent", "icon": "send", "label": "SENT"},
    "drafts": {"title": "Drafts", "icon": "draft", "label": "DRAFT"},
    "all": {"title": "All mail", "icon": "all_inbox"},
    "archive": {"title": "Archive", "icon": "archive", "query": "-in:inbox -in:trash -in:spam"},
    "important": {"title": "Important", "icon": "label_important", "label": "IMPORTANT"},
    "spam": {"title": "Spam", "icon": "report", "label": "SPAM"},
    "trash": {"title": "Trash", "icon": "delete", "label": "TRASH"},
}


def requested_mail_folder():
    account = active_email_account(g.user)
    folder = request.args.get("folder") or request.form.get("folder") or "inbox"
    if folder not in GMAIL_FOLDERS:
        abort(404)
    if request.args.get("account") == "all":
        if folder != "inbox": abort(404)
        return folder
    if account["kind"] == "imap" and folder not in {"inbox","starred",*account["config"]["folders"]}:
        abort(404)
    if account["kind"] == "microsoft" and folder not in {"all","starred",*graph_mail.FOLDERS}:
        abort(404)
    return folder


def cached_mail_preview(user, folder, account=None):
    """Render a small local preview without contacting a provider."""
    account = account or active_email_account(user)
    if account["kind"] != "gmail":
        prefix = ("imap-" if account["kind"] == "imap" else "ms-") + account["config"]["account_id"] + "-"
        if account["kind"] == "imap": prefix += email_providers.folder_id(account["config"],folder) + "-"
        prefix += "%"
        label = GMAIL_FOLDERS[folder].get("label")
        rows = get_db().execute("SELECT metadata FROM gmail_cache WHERE user_id = ? AND message_id LIKE ? AND metadata IS NOT NULL ORDER BY metadata_at DESC LIMIT 25", (user["id"],prefix)).fetchall()
        values = [json.loads(row["metadata"]) for row in rows]
        return [value for value in values if (not label or label in value.get("label_ids",[])) and (account['kind']=='imap' or folder in {'all','starred'} or value.get('mail_folder')==folder)]
    page = get_db().execute(
        "SELECT message_ids FROM gmail_folder_pages "
        "WHERE user_id = ? AND folder = ? AND query = '' AND cursor = ''",
        (user["id"], gmail_folder_key(account, folder)),
    ).fetchone()
    if page:
        ids = json.loads(page["message_ids"])[:MAIL_BATCH_SIZE]
        return [message for message_id in ids
                if (message := gmail_cache_get(user["id"], message_id)) is not None]
    # Old inbox caches have no label_ids. Only treat those as inbox messages.
    label = GMAIL_FOLDERS[folder].get("label")
    if folder == "snoozed":
        return []
    rows = get_db().execute(
        """SELECT metadata FROM gmail_cache WHERE user_id = ? AND metadata IS NOT NULL
           AND message_id NOT LIKE 'imap-%' AND message_id NOT LIKE 'ms-%'
           AND ((? = 'gmail' AND message_id NOT LIKE 'gm-%') OR (? != 'gmail' AND message_id LIKE ?))
           AND (? = 'all' OR EXISTS (
               SELECT 1 FROM json_each(COALESCE(json_extract(metadata, '$.label_ids'), '["INBOX"]'))
               WHERE value = ?))
           ORDER BY CAST(json_extract(metadata, '$.internal_date') AS INTEGER) DESC LIMIT ?""",
        (user["id"], account['key'], account['key'], gmail_message_key(account, '') + '%', folder, label, MAIL_BATCH_SIZE),
    ).fetchall()
    return [json.loads(row["metadata"]) for row in rows]


def fetch_mail_page(user, folder, cursor="", query="", refresh=False, account=None):
    """Fetch one Gmail page, never walk the entire mailbox."""
    account = account or active_email_account(user)
    if account["kind"] != "gmail":
        if "\r" in query or "\n" in query:
            raise ValueError("Mail searches cannot contain new lines.")
        if account["kind"] == "imap":
            payloads, next_cursor, total = email_providers.list_messages(account["config"],cursor,query,folder)
        else:
            payloads, next_cursor, total = graph_mail.list_messages(microsoft_access_token(account),account["config"],folder,query,cursor)
        messages = [gmail_metadata_from_payload(payload,payload["id"]) for payload in payloads]
        for message in messages: message['mail_folder']='inbox' if folder=='starred' and account['kind']=='imap' else folder
        for message in messages: gmail_cache_put(user["id"],message["id"],metadata=message)
        return messages,next_cursor,total
    token = get_gmail_access_token(user, account)
    if not token:
        raise RuntimeError("Connect Google to load your email.")
    headers = {"Authorization": "Bearer " + token}
    db = get_db()
    folder_key = gmail_folder_key(account, folder)
    cached = db.execute(
        "SELECT * FROM gmail_folder_pages WHERE user_id = ? AND folder = ? AND query = ? AND cursor = ?",
        (user["id"], folder_key, query, cursor),
    ).fetchone()
    if cached and not refresh and time.time() - cached["listed_at"] < GMAIL_LIST_TTL:
        ids = json.loads(cached["message_ids"])
        next_cursor, total = cached["next_cursor"], cached["total"]
    else:
        config = GMAIL_FOLDERS[folder]
        params = {"maxResults": MAIL_BATCH_SIZE, "includeSpamTrash": folder in {"spam", "trash"}}
        if config.get("label"):
            params["labelIds"] = config["label"]
        search = " ".join(part for part in (config.get("query", ""), query) if part)
        if search:
            params["q"] = search
        if cursor:
            params["pageToken"] = cursor
        response = google_requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers, params=params, timeout=(5, 15),
        )
        response.raise_for_status()
        payload = response.json()
        ids = [gmail_message_key(account, item["id"]) for item in payload.get("messages", []) if item.get("id")][:MAIL_BATCH_SIZE]
        next_cursor = payload.get("nextPageToken")
        total = payload.get("resultSizeEstimate", len(ids))
        db.execute(
            """INSERT INTO gmail_folder_pages VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, folder, query, cursor) DO UPDATE SET
               message_ids = excluded.message_ids, next_cursor = excluded.next_cursor,
               total = excluded.total, listed_at = excluded.listed_at""",
            (user["id"], folder_key, query, cursor, json.dumps(ids), next_cursor, total, time.time()),
        )
        db.commit()
    messages, missing = {}, []
    for message_id in ids:
        metadata = None if refresh else gmail_cache_get(user["id"], message_id)
        if metadata is not None and "reply_to" not in metadata:
            metadata = None
        if metadata is not None:
            messages[message_id] = metadata
        else:
            missing.append(message_id)
    # At most 25 metadata requests per page; other pages wait for scrolling.
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_gmail_detail, headers, gmail_raw_message_id(account, item)): item for item in missing}
        for future in as_completed(futures):
            message_id = futures[future]
            try:
                metadata = future.result()
            except requests.HTTPError as error:
                if gmail_error_status(error) in {404, 410}:
                    continue
                raise
            metadata['id'] = message_id
            gmail_cache_put(user["id"], message_id, metadata=metadata)
            messages[message_id] = metadata
    return [messages[item] for item in ids if item in messages], next_cursor, total


def fetch_all_inboxes_page(user, cursor="", query="", refresh=False):
    accounts = email_accounts(user)
    signer = URLSafeSerializer(app.config['SECRET_KEY'], salt='all-inboxes')
    state = {account['key']: {'cursor': '', 'total': 0} for account in accounts}
    if cursor:
        try:
            saved = signer.loads(cursor)
        except BadSignature as error:
            raise ValueError('Invalid inbox page.') from error
        if saved.get('user') != user['id'] or saved.get('query') != query:
            raise ValueError('Invalid inbox page.')
        state = {account['key']: saved['accounts'].get(account['key'], {'cursor':'', 'total':0}) for account in accounts}
    messages, failures = [], []
    for account in accounts:
        page = state[account['key']]
        if page.get('failed'):
            failures.append(account['email'])
        if page['cursor'] is None: continue
        try:
            batch, next_cursor, total = fetch_mail_page(user, 'inbox', page['cursor'], query, refresh, account=account)
        except (RuntimeError, requests.RequestException, ValueError, KeyError, OSError, imaplib.IMAP4.error):
            failures.append(account['email'])
            page['cursor'] = None
            page['failed'] = True
            continue
        messages.extend({**message, 'mail_account_key':account['key'], 'mail_account_email':account['email'], 'mail_folder':'inbox'} for message in batch)
        page.update(cursor=next_cursor or None, total=total)
    messages.sort(key=lambda message: int(message.get('internal_date') or 0), reverse=True)
    next_cursor = signer.dumps({'user':user['id'], 'query':query, 'accounts':state}) if any(page['cursor'] is not None for page in state.values()) else None
    warning = 'Could not load ' + ', '.join(failures) + '. Refresh to try these accounts again.' if failures else ''
    total = None if failures or any(page['total'] is None for page in state.values()) else sum(page['total'] for page in state.values())
    return messages, next_cursor, total, warning


@app.get('/api/mail/messages')
def mailbox_messages():
    folder = requested_mail_folder()
    query = request.args.get("search", "").strip()[:500]
    category = request.args.get("category", "")
    aggregate = request.args.get('account') == 'all'
    if not aggregate and active_email_account(g.user)["kind"] == "gmail" and folder == "inbox" and category in {"primary", "updates", "social"}:
        query = " ".join(filter(None, (query, "category:" + category)))
    try:
        warning = ''
        if aggregate:
            messages, next_cursor, total, warning = fetch_all_inboxes_page(g.user, request.args.get('cursor', ''), query, request.args.get('refresh') == '1')
        else:
            messages, next_cursor, total = fetch_mail_page(
                g.user, folder, request.args.get("cursor", ""), query,
                refresh=request.args.get("refresh") == "1",
            )
    except RuntimeError as error:
        return jsonify(error=str(error), reconnect=True), 409
    except requests.HTTPError as error:
        return jsonify(error=gmail_error_message(error), reconnect=gmail_error_status(error) in {401, 403}), 502
    except (requests.RequestException, KeyError, ValueError, OSError, imaplib.IMAP4.error):
        app.logger.warning("Could not load mail page for user id=%s", g.user["id"])
        return jsonify(error="Could not load messages. Please try again."), 502
    return jsonify(
        html=render_template('mail_rows.html', messages=[{**message, **email_reply_info(message), 'otp_code':extract_otp_code(message.get('subject',''),message.get('preview',''))} for message in messages], folder=folder, mail_account_key='all' if aggregate else active_email_account(g.user)["key"]),
        next_cursor=next_cursor, total=total, count=len(messages), warning=warning,
    )


@app.post('/api/mail/gmail/status')
def gmail_message_states():
    account = active_email_account(g.user)
    if account['kind'] != 'gmail': abort(404)
    identifiers = list(dict.fromkeys(request.form.getlist('message_ids')))
    if not 1 <= len(identifiers) <= 50:
        return jsonify(error='Check up to 50 loaded messages at a time.'), 400
    try:
        raw_ids = {identifier:gmail_raw_message_id(account, identifier) for identifier in identifiers}
    except ValueError as error:
        return jsonify(error=str(error)), 400
    try:
        token = get_gmail_access_token(g.user)
        if not token: return jsonify(error='Reconnect Gmail to update read status.', reconnect=True), 409
        db = get_db()
        cached = {identifier:db.execute('SELECT metadata, metadata_at FROM gmail_cache WHERE user_id=? AND message_id=?', (g.user['id'],identifier)).fetchone() for identifier in identifiers}
        def fetch_labels(raw_id):
            response = google_requests.get(f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{raw_id}',
                headers={'Authorization':'Bearer '+token}, params={'format':'minimal','fields':'id,labelIds'}, timeout=(5,10))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict): raise ValueError('Invalid Gmail message.')
            labels = payload.get('labelIds', [])
            if payload.get('id') != raw_id or not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
                raise ValueError('Invalid Gmail message labels.')
            return 'UNREAD' in labels
        states, remote = [], {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_labels, raw_id):identifier for identifier,raw_id in raw_ids.items()}
            for future in as_completed(futures):
                try: unread = future.result()
                except requests.HTTPError as error:
                    if gmail_error_status(error) in {404,410}: continue
                    raise
                remote[futures[future]] = unread
        for identifier, unread in remote.items():
            previous = cached[identifier]
            if previous and previous['metadata']:
                metadata = json.loads(previous['metadata'])
                labels = set(metadata.get('label_ids', []))
                labels.add('UNREAD') if unread else labels.discard('UNREAD')
                metadata.update(unread=unread, label_ids=sorted(labels))
                # Do not overwrite a local action that completed while Gmail was being checked.
                updated = db.execute('UPDATE gmail_cache SET metadata=? WHERE user_id=? AND message_id=? AND metadata=? AND metadata_at IS ?',
                    (json.dumps(metadata),g.user['id'],identifier,previous['metadata'],previous['metadata_at']))
                if not updated.rowcount:
                    current = db.execute('SELECT metadata FROM gmail_cache WHERE user_id=? AND message_id=?', (g.user['id'],identifier)).fetchone()
                    if current and current['metadata']: unread = json.loads(current['metadata']).get('unread', unread)
            states.append({'id':identifier, 'unread':unread})
        if account['key'] == 'gmail': db.execute('DELETE FROM gmail_mailbox_counts WHERE user_id=?', (g.user['id'],))
        else: db.execute('DELETE FROM gmail_account_counts WHERE user_id=? AND account_key=?', (g.user['id'],account['key']))
        db.commit()
        return jsonify(messages=states, counts=mailbox_counts().get_json())
    except requests.HTTPError as error:
        get_db().rollback()
        return jsonify(error=gmail_error_message(error), reconnect=gmail_error_status(error) in {401,403}), 502
    except (ValueError, KeyError, requests.RequestException):
        get_db().rollback()
        return jsonify(error='Gmail read status could not be updated. Try Refresh.'), 502


@app.get('/api/mail/counts')
def mailbox_counts(account=None):
    if account is None and request.args.get('account') == 'all':
        return jsonify(all_inboxes=sum(mailbox_counts(account).get_json().get('inbox', 0) for account in email_accounts(g.user)))
    account = account or active_email_account(g.user)
    if account["kind"] != "gmail":
        try:
            if account["kind"] == "microsoft":
                data = graph_mail.request(microsoft_access_token(account),"GET","/me/mailFolders/inbox",params={"$select":"unreadItemCount"})
                return jsonify(inbox=data.get("unreadItemCount",0))
            with email_providers.imap_connect(account["config"]) as client:
                status,rows = client.status(email_providers.mailbox_name(account["config"],"inbox"),"(UNSEEN)")
                email_providers.check(status,"Counts unavailable.")
                match=re.search(rb"UNSEEN (\d+)",rows[0])
                return jsonify(inbox=int(match[1]) if match else 0)
        except (RuntimeError,requests.RequestException,OSError,imaplib.IMAP4.error):
            return jsonify({})
    cached = get_db().execute(
        "SELECT counts, updated_at FROM gmail_mailbox_counts WHERE user_id = ?", (g.user["id"],)
    ).fetchone() if account['key'] == 'gmail' else get_db().execute(
        "SELECT counts, updated_at FROM gmail_account_counts WHERE user_id=? AND account_key=?", (g.user['id'],account['key'])
    ).fetchone()
    if cached and time.time() - cached["updated_at"] < 60 and request.args.get("refresh") != "1":
        return jsonify(json.loads(cached["counts"]))
    try:
        try:
            token = get_gmail_access_token(g.user, account)
        except requests.HTTPError as error:
            if gmail_error_status(error) in {401, 403}:
                return jsonify(error="Reconnect Gmail to continue scanning.", reconnect=True), 401
            return jsonify(error="Could not connect to Gmail. Please try again."), 502
        except requests.RequestException:
            return jsonify(error="Could not connect to Gmail. Please try again."), 502
        if not token:
            return jsonify({})
        counts = {}
        for folder, label in (("inbox", "INBOX"), ("drafts", "DRAFT")):
            response = google_requests.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/labels/" + label,
                headers={"Authorization": "Bearer " + token}, timeout=(5, 10),
            )
            response.raise_for_status()
            info = response.json()
            counts[folder] = info.get("messagesUnread", 0) if folder == "inbox" else info.get("messagesTotal", 0)
        if account['key'] == 'gmail':
            get_db().execute("INSERT OR REPLACE INTO gmail_mailbox_counts VALUES (?, ?, ?)", (g.user["id"], json.dumps(counts), time.time()))
        else:
            get_db().execute("INSERT OR REPLACE INTO gmail_account_counts VALUES (?, ?, ?, ?)", (g.user['id'],account['key'],json.dumps(counts),time.time()))
        get_db().commit()
        return jsonify(counts)
    except (requests.RequestException, KeyError, ValueError):
        return jsonify(json.loads(cached["counts"]) if cached else {})


@app.post('/api/mail/action')
def mail_action():
    changes = {
        "archive": ([], ["INBOX"]), "trash": (["TRASH"], ["INBOX"]),
        "restore": (["INBOX"], ["TRASH"]), "read": ([], ["UNREAD"]),
        "unread": (["UNREAD"], []), "star": (["STARRED"], []), "unstar": ([], ["STARRED"]),
    }
    action = request.form.get("action")
    ids = list(dict.fromkeys(request.form.getlist("message_ids")))
    if action not in changes or not 1 <= len(ids) <= 1000 or any(
        not re.fullmatch(r"[A-Za-z0-9_-]{1,1000}", item) for item in ids
    ):
        return jsonify(error="Select messages and choose a valid action."), 400
    account = active_email_account(g.user)
    if account["kind"] != "gmail":
        try:
            if account["kind"] == "imap":
                email_providers.change_messages(account["config"],ids,action,request.form.get("folder","inbox"))
            else:
                graph_mail.change_messages(microsoft_access_token(account),account["config"],ids,action)
        except (RuntimeError,ValueError,requests.RequestException,OSError,imaplib.IMAP4.error):
            return jsonify(error="The mail action could not be completed. Refresh to check the current state."),502
        for message_id in ids:
            metadata=gmail_cache_get(g.user["id"],message_id)
            if metadata:
                add,remove=changes[action]
                labels=(set(metadata.get('label_ids',[])) | set(add)) - set(remove)
                metadata.update(label_ids=sorted(labels),unread='UNREAD' in labels,starred='STARRED' in labels)
                if action in {"archive","trash","restore"}: get_db().execute("DELETE FROM gmail_cache WHERE user_id=? AND message_id=?",(g.user["id"],message_id))
                else: gmail_cache_put(g.user["id"],message_id,metadata=metadata)
        get_db().commit()
        return jsonify(action=action,ids=ids)
    add, remove = changes[action]
    try:
        raw_ids = [gmail_raw_message_id(account, identifier) for identifier in ids]
        token = get_gmail_access_token(g.user)
        if not token:
            return jsonify(error="Connect Google to change your email.", reconnect=True), 409
        response = google_requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/batchModify",
            headers={"Authorization": "Bearer " + token},
            json={"ids": raw_ids, "addLabelIds": add, "removeLabelIds": remove}, timeout=(5, 20),
        )
        response.raise_for_status()
    except requests.HTTPError as error:
        if gmail_error_status(error) in {401, 403}:
            return jsonify(error="Reconnect Google to allow archiving, starring and changing messages.", reconnect=True), 403
        return jsonify(error=gmail_error_message(error)), 502
    except (ValueError, requests.RequestException):
        return jsonify(error="The message action failed. Please try again."), 502
    db = get_db()
    for message_id in ids:
        metadata = gmail_cache_get(g.user["id"], message_id)
        if metadata is not None:
            labels = (set(metadata.get("label_ids", ["INBOX"])) | set(add)) - set(remove)
            metadata.update(label_ids=sorted(labels), unread="UNREAD" in labels, starred="STARRED" in labels)
            gmail_cache_put(g.user["id"], message_id, metadata=metadata)
    if account['key'] == 'gmail':
        db.execute("DELETE FROM gmail_folder_pages WHERE user_id=? AND folder NOT LIKE 'gm:%'", (g.user['id'],))
        for table in ('gmail_mailbox_counts','gmail_sync_state'):
            db.execute(f"DELETE FROM {table} WHERE user_id=?", (g.user['id'],))
    else:
        db.execute("DELETE FROM gmail_folder_pages WHERE user_id=? AND folder LIKE ?", (g.user['id'],gmail_folder_key(account,'')+'%'))
        db.execute("DELETE FROM gmail_account_counts WHERE user_id=? AND account_key=?", (g.user['id'],account['key']))
    db.commit()
    return jsonify(action=action, ids=ids)


def paginate_messages(messages, page):
    total = len(messages)
    pages = max(1, (total + INBOX_PAGE_SIZE - 1) // INBOX_PAGE_SIZE)
    page = min(max(page or 1, 1), pages)
    start = (page - 1) * INBOX_PAGE_SIZE
    return {
        "messages": messages[start:start + INBOX_PAGE_SIZE],
        "page": page,
        "pages": pages,
        "first": start + 1 if total else 0,
        "last": min(start + INBOX_PAGE_SIZE, total),
    }


@app.route('/inbox')
def inbox(compose_draft=None):
    folder = requested_mail_folder()
    account = active_email_account(g.user)
    aggregate = request.args.get('account') == 'all'
    accounts = email_accounts(g.user)
    preview = [{**message, 'mail_account_key':source['key'], 'mail_account_email':source['email'], 'mail_folder':'inbox'}
               for source in accounts for message in cached_mail_preview(g.user, 'inbox', account=source)] if aggregate else cached_mail_preview(g.user, folder)
    preview.sort(key=lambda message: int(message.get('internal_date') or 0), reverse=True)
    messages = [{**message, **email_reply_info(message), 'otp_code':extract_otp_code(message.get('subject',''),message.get('preview',''))} for message in preview]
    available = GMAIL_FOLDERS
    if account["kind"] == "imap": available = {key:value for key,value in GMAIL_FOLDERS.items() if key in {"inbox","starred",*account["config"]["folders"]}}
    elif account["kind"] == "microsoft": available = {key:value for key,value in GMAIL_FOLDERS.items() if key in {"all","starred",*graph_mail.FOLDERS}}
    return render_template(
        'mail.html', messages=messages, folder=folder, folders=available, mail_accounts=accounts, mail_account_key='all' if aggregate else account['key'], mail_kind='aggregate' if aggregate else account['kind'],
        folder_title='All inboxes' if aggregate else GMAIL_FOLDERS[folder]["title"], stats=make_stats(messages), compose_account_key=account['key'],
        compose_draft=compose_draft, mail_account_email=account['email'], app_connections=workspace_connections(g.user),
    )


def workspace_connections(user):
    connections = []
    chat = get_integration(user['id'], 'google_chat')
    account = next((account for account in email_accounts(user) if account['key'] == chat.get('account_key') and account['kind'] == 'gmail'), None) if chat else None
    stored = (get_google_token(user) if account['key'] == 'gmail' else account['config']['token']) if account else {}
    connected = bool(account and set(google_chat.SCOPES.split()).issubset(set(stored.get('scope','').split())))
    connections.append({'key':'google-chat','name':'Google Chat','subtitle':account['email'] if account else 'Chats and spaces',
        'connected':connected, 'messages_url':url_for('google_chat_spaces') if connected else ''})
    for provider, name in [('telegram','Telegram'), ('teams','Microsoft Teams'), ('discord','Discord'), ('whatsapp','WhatsApp')]:
        config = get_integration(user['id'], provider)
        if not config or (provider == 'telegram' and config.get('stage') != 'connected'):
            continue
        subtitle = config.get('channel_name') or config.get('display_phone_number') or (config.get('account') or {}).get('username') or 'Recent conversations'
        connections.append({'key':provider,'name':name,'subtitle':subtitle,'messages_url':url_for('teams_conversations') if provider == 'teams' else url_for('integration_messages',provider=provider)})
    for spec in SOCIAL_PROVIDERS:
        if spec['key'] in integration_catalog.PLACEHOLDER_PROVIDERS:
            continue
        if get_integration(user['id'],'social:'+spec['key']):
            connections.append({'key':spec['key'],'name':spec['name'],'subtitle':'Connected integration','messages_url':''})
    return connections


@app.route('/mail')
def mail():
    return inbox()


def fetch_email_message(user, account, message_id, folder):
    if account["kind"] == "gmail":
        if message_id.startswith(("imap-", "ms-")):
            raise ValueError("This email belongs to a different account.")
        return fetch_gmail_message(user, message_id, for_reply=True)
    config = account["config"]
    if account["kind"] == "imap":
        email_providers.parse_id(config, message_id, folder=folder)
        payload = email_providers.read_message(config, message_id, folder)
    else:
        graph_mail.raw_id(config, message_id)
        payload = graph_mail.read_message(microsoft_access_token(account), config, message_id, folder)
    metadata = gmail_metadata_from_payload(payload, message_id)
    metadata['mail_folder'] = 'inbox' if folder == 'starred' and account['kind'] == 'imap' else folder
    body = decode_gmail_body(payload.get("payload", {}))
    gmail_cache_put(user["id"], message_id, metadata=metadata, body=body)
    return {**metadata, "body": body}


@app.get('/api/mail/conversations/<message_id>')
def mail_conversation(message_id):
    account = active_email_account(g.user)
    folder = requested_mail_folder()
    try:
        if account['kind'] == 'gmail': gmail_raw_message_id(account, message_id)
        elif account['kind'] == 'microsoft': graph_mail.raw_id(account['config'], message_id)
        else: email_providers.parse_id(account['config'], message_id, folder=folder)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    try:
        current = gmail_cache_get(g.user['id'], message_id)
        if not current:
            current = fetch_email_message(g.user, account, message_id, folder)
        if not current: raise RuntimeError('Reconnect the email account to load the conversation.')
        messages = []
        if account['kind'] == 'gmail':
            thread_id = current.get('thread_id', '')
            token = get_gmail_access_token(g.user)
            if not thread_id and token:
                current = _fetch_gmail_detail({'Authorization':'Bearer '+token}, gmail_raw_message_id(account, message_id))
                current['id'] = message_id
                thread_id = current.get('thread_id', '')
            if thread_id and token:
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', thread_id): raise ValueError('Invalid conversation identifier.')
                response = google_requests.get('https://gmail.googleapis.com/gmail/v1/users/me/threads/'+thread_id,
                    headers={'Authorization':'Bearer '+token}, params={'format':'metadata',
                    'metadataHeaders':['From','To','Reply-To','Subject','Date','Message-ID','References','In-Reply-To']}, timeout=(5,20))
                response.raise_for_status()
                for payload in response.json().get('messages', []):
                    identifier = gmail_message_key(account, payload['id'])
                    gmail_raw_message_id(account, identifier)
                    metadata = gmail_metadata_from_payload(payload, identifier)
                    if metadata['thread_id'] != thread_id: raise ValueError('Invalid conversation message.')
                    metadata['id'] = identifier
                    messages.append(metadata)
            elif thread_id:
                rows = get_db().execute("SELECT metadata FROM gmail_cache WHERE user_id=? AND json_extract(metadata,'$.thread_id')=?", (g.user['id'],thread_id)).fetchall()
                for row in rows:
                    metadata = json.loads(row['metadata'])
                    try: gmail_raw_message_id(account, metadata['id'])
                    except ValueError: continue
                    messages.append(metadata)
        elif account['kind'] == 'microsoft':
            payloads = graph_mail.conversation_messages(microsoft_access_token(account), account['config'], message_id, current.get('thread_id'))
            messages = [gmail_metadata_from_payload(payload, payload['id']) for payload in payloads]
        else:
            payloads = email_providers.conversation_messages(account['config'], current, folder)
            for payload in payloads:
                metadata = gmail_metadata_from_payload(payload, payload['id'])
                metadata['mail_folder'] = payload['mail_folder']
                messages.append(metadata)
        by_id = {message['id']:message for message in messages}
        by_id.setdefault(message_id, current)
        messages = sorted(by_id.values(), key=lambda message:(message.get('internal_date',0), message['id']))
        return jsonify(html=render_template('conversation.html', messages=messages, current_id=message_id,
            mail_account_key=account['key'], folder=folder) if len(messages)>1 else '', count=len(messages))
    except (RuntimeError, ValueError, KeyError, requests.RequestException, OSError, imaplib.IMAP4.error):
        return jsonify(error='The conversation could not be loaded. Please try again.'), 502


@app.route('/message/<message_id>')
def message_detail(message_id):
    folder = requested_mail_folder()
    account = active_email_account(g.user)
    try:
        message = fetch_email_message(g.user, account, message_id, folder)
        if message is None:
            raise RuntimeError("Connect Google to read this email.")
        message = {**message, **email_reply_info(message, account)}
        body = message['body']
        body_text = (body.get('text') or email_html_text(body.get('html', ''))) if isinstance(body, dict) else str(body)
        message['otp_code'] = extract_otp_code(message['subject'], body_text + '\n' + message.get('preview', ''))
    except (RuntimeError, requests.RequestException, KeyError, ValueError, OSError, imaplib.IMAP4.error) as error:
        if request.args.get("pane") == "1":
            return render_template('message_error.html', error="Could not open this email. Check the account connection and try again."), 502
        return render_template(
            'message_unavailable.html', folder=folder, folder_title=GMAIL_FOLDERS[folder]["title"],
            error=str(error) if isinstance(error, RuntimeError) else "Could not open this email. Please try again.",
        )
    return render_template(
        'message_pane.html' if request.args.get("pane") == "1" else 'message.html',
        message=message, folder=folder, folder_title=GMAIL_FOLDERS[folder]["title"], mail_account_key=account['key'],
        mail_account_email=account['email'], reply_to=reply_address(message, account),
        reply_subject=message['subject'] if re.match(r'^re\s*:', message['subject'], re.I) else 'Re: ' + message['subject'],
    )


@app.post('/compose')
def compose():
    """Send a message from the in-page composer. There is no compose page."""
    recipient = normalize_email(request.form.get('to', ''))
    subject = request.form.get('subject') or 'No subject'
    body = request.form.get('body') or ''
    account = active_email_account(g.user)
    folder = requested_mail_folder()
    reply_id = request.form.get('reply_id', '')
    error_message = ''
    email_error = ''
    if not valid_email(recipient):
        error_message = email_error = "Enter a valid recipient email address."
    elif '\r' in subject or '\n' in subject:
        error_message = "The email subject must be a single line."
    elif not body.strip():
        error_message = "Write a message before sending."
    else:
        try:
            if email_error := email_address_error(recipient, check_domain=True):
                raise RuntimeError(email_error)
            sent_warning=None
            original = fetch_email_message(g.user, account, reply_id, folder) if reply_id else None
            if reply_id and original is None:
                raise RuntimeError("Reconnect the email account before replying.")
            if original and (not email_reply_info(original, account)["can_reply"] or email_reply_info({"email": recipient})["is_no_reply"]):
                raise RuntimeError("Replies are disabled for this email because it has no usable reply address.")
            if account["kind"] == "gmail":
                if original: send_gmail_message(g.user, recipient, subject, body, reply=original)
                else: send_gmail_message(g.user, recipient, subject, body)
            elif account["kind"] == "microsoft":
                if original: graph_mail.reply_message(microsoft_access_token(account),account['config'],reply_id,recipient,subject,body)
                else: graph_mail.send_message(microsoft_access_token(account),recipient,subject,body)
            else:
                email=EmailMessage(); email["From"]=account["email"]; email["To"]=recipient; email["Subject"]=subject; email.set_content(body)
                if original: add_reply_headers(email, original)
                sent_warning=email_providers.send_message(account["config"],email)
        except RuntimeError as error:
            error_message = str(error)
        except (ValueError, requests.RequestException,OSError,imaplib.IMAP4.error,smtplib.SMTPException):
            error_message = "The mail server could not send the message. Please try again."
        else:
            flash(sent_warning or f"Message sent to {recipient} successfully.", "info" if sent_warning else "success")
            return redirect(url_for('inbox', account=account['key'], folder=folder))
    if not email_error:
        flash(error_message,'error')
    return inbox(compose_draft={'to': recipient, 'subject': subject, 'body': body, 'reply_id': reply_id, 'error':error_message, 'email_error':email_error})


@app.route('/settings')
def settings():
    return render_template('settings.html')


@app.get('/integrations')
def integrations(email_error='', email_value=''):
    accounts = email_accounts(g.user)
    chat_config = get_integration(g.user['id'], 'google_chat')
    chat_account = next((account for account in accounts if chat_config and account['key'] == chat_config.get('account_key') and account['kind'] == 'gmail'), None)
    telegram = get_integration(g.user["id"], "telegram")
    telegram_stage = telegram.get("stage") if telegram else None
    telegram_account = telegram.get("account") if telegram else None
    whatsapp = get_integration(g.user["id"], "whatsapp")
    discord = get_integration(g.user["id"], "discord")
    teams = get_integration(g.user['id'], 'teams')
    social_cards = [
        {
            "spec": spec,
            "config": get_integration(g.user["id"], "social:" + spec["key"]),
        }
        for spec in SOCIAL_PROVIDERS
    ]
    google_ready = bool(app.config['GOOGLE_CLIENT_ID'] and app.config['GOOGLE_CLIENT_SECRET'])
    microsoft_ready = bool(app.config['MICROSOFT_CLIENT_ID'] and app.config['MICROSOFT_CLIENT_SECRET'])
    configs = {'telegram': telegram, 'google-chat': chat_config if chat_account else None,
               'teams': teams, 'discord': discord, 'whatsapp': whatsapp,
               **{card['spec']['key']: card['config'] for card in social_cards}}
    catalog = []
    for spec in integration_catalog.APPS:
        key = spec['key']
        placeholder = key in integration_catalog.PLACEHOLDER_PROVIDERS
        connected = (any(account['kind'] == {'gmail':'gmail', 'outlook':'microsoft', 'imap':'imap'}[key]
                         for account in accounts) if key in {'gmail', 'outlook', 'imap'} else bool(configs.get(key)))
        pending = key == 'telegram' and telegram_stage in {'code', 'password'}
        if key == 'telegram': connected = telegram_stage == 'connected'
        ready = (google_ready if key in {'gmail', 'google-chat'} else
                 microsoft_ready if key in {'outlook', 'teams'} else
                 telegram_available() if key == 'telegram' else True)
        catalog.append({**spec, 'placeholder': placeholder, 'connected': connected and not placeholder,
                        'pending': pending, 'ready': ready and not placeholder})
    open_app = request.args.get('app', '')
    if email_error: open_app = 'imap'
    elif telegram_stage in {'code', 'password'} and not open_app: open_app = 'telegram'
    return render_template(
        'integrations.html',
        integration_apps=catalog,
        connected_count=sum(item['connected'] for item in catalog),
        open_app=open_app if open_app in integration_catalog.APPS_BY_KEY and open_app not in integration_catalog.PLACEHOLDER_PROVIDERS else '',
        whatsapp_webhook_ready=bool(app.config.get('WHATSAPP_APP_SECRET')),
        oauth_callbacks={
            'google': app.config['GOOGLE_REDIRECT_URI'] or url_for('google_callback', _external=True),
            'outlook': app.config['MICROSOFT_REDIRECT_URI'] or url_for('microsoft_callback', _external=True),
            'teams': app.config['MICROSOFT_TEAMS_REDIRECT_URI'] or url_for('teams_callback', _external=True),
        },
        email_error=email_error, email_value=email_value,
        telegram=telegram,
        telegram_stage=telegram_stage,
        telegram_account=telegram_account,

        telegram_available=telegram_available(),
        whatsapp=whatsapp,
        whatsapp_webhook_url=url_for('whatsapp_webhook', _external=True),
        discord=discord,
        teams=teams,
        google_chat=chat_config if chat_account else None,
        google_chat_email=chat_account['email'] if chat_account else None,

        social_cards=social_cards,
        email_presets=email_providers.PROVIDERS, email_connections=accounts,
    )


@app.post('/api/integrations/<provider>/check')
def check_integration(provider):
    if provider not in integration_catalog.APPS_BY_KEY or provider in {'gmail', 'outlook', 'imap'}:
        abort(404)
    if provider in integration_catalog.PLACEHOLDER_PROVIDERS:
        return jsonify(error=integration_catalog.APPS_BY_KEY[provider]['name'] + ' is coming soon.'), 409
    if provider == 'google-chat':
        def check_chat(token, me, account):
            google_chat.request(token, 'GET', 'spaces', params={'pageSize': 1})
            return jsonify(message='Google Chat access confirmed.')
        return _google_chat_api(check_chat)
    key = 'social:' + provider if provider in SOCIAL_PROVIDERS_BY_KEY else provider
    config = get_integration(g.user['id'], key)
    if not config or (provider in {'telegram', 'teams'} and config.get('stage') != 'connected'):
        return jsonify(error='Connect this app first.'), 409
    try:
        if provider == 'telegram':
            async def check_telegram():
                client = _telegram_client(config)
                await client.connect()
                try:
                    if not await client.is_user_authorized():
                        raise RuntimeError('Your Telegram session expired. Disconnect and sign in again.')
                    await client.get_me()
                finally:
                    await client.disconnect()
            with _telegram_lock(g.user['id']):
                asyncio.run(check_telegram())
        elif provider == 'discord':
            discord_request(config, 'GET', '/users/@me')
            discord_request(config, 'GET', '/channels/' + config['channel_id'])
        elif provider == 'whatsapp':
            whatsapp_request(config, 'GET', params={'fields': WHATSAPP_FIELDS})
        elif provider == 'teams':
            token = microsoft_access_token({'key': 'teams', 'config': config})
            graph_mail.request(token, 'GET', '/me/chats', params={'$top': 1})
        elif provider == 'bluesky':
            social_request('https://bsky.social/xrpc/com.atproto.server.getSession', config['access_token'])
        else:
            social_profile(provider, dict(config))
    except requests.RequestException:
        return jsonify(error='This app could not be reached. Check your connection and try again.'), 502
    except Exception as error:
        app.logger.warning('Integration check failed for provider=%s user id=%s', provider, g.user['id'])
        message = telegram_error_text(error) if provider == 'telegram' else str(error)
        return jsonify(error=message or 'Access could not be confirmed. Reconnect this app.'), 502
    return jsonify(message='Account access confirmed. No message was sent.')


@app.post('/integrations/email/connect')
def connect_email():
    preset=email_providers.PROVIDERS_BY_KEY.get(request.form.get("provider",""))
    if preset is None: abort(400)
    email=normalize_email(request.form.get("email","")); password=request.form.get("password","")
    if error := email_address_error(email):
        return integrations(email_error=error, email_value=email)
    try:
        if not password or len(password)>1024 or "\r" in password or "\n" in password:
            raise ValueError("Enter an email address and a valid password or app password.")
        config={"kind":"imap","name":preset["name"],"email":email,"password":password,"account_id":hashlib.sha256(email.encode()).hexdigest()[:12]}
        config['save_sent']=request.form.get('save_sent','true' if preset.get('save_sent',True) else 'false')=='true'
        for field in ('imap_username','smtp_username','smtp_password'):
            value=request.form.get(field,'')
            if len(value)>1024 or '\r' in value or '\n' in value: raise ValueError('Invalid mail login credentials.')
            if value: config[field]=value
        for field in ("imap_host","smtp_host"):
            config[field]=email_providers.validate_host(request.form.get(field,"").strip() or preset[field])
        for field in ("imap_port","smtp_port"):
            config[field]=int(request.form.get(field,"") or preset[field])
            if not 1<=config[field]<=65535: raise ValueError("Choose valid mail server ports.")
        for field in ("imap_security","smtp_security"):
            config[field]=request.form.get(field) or preset[field]
            if config[field] not in {"ssl","starttls"}: raise ValueError("Mail connections require TLS.")
        with email_providers.imap_connect(config) as client: config["folders"]=email_providers.discover_folders(client)
        with email_providers.smtp_connect(config): pass
        key="email:imap:"+config["account_id"]; save_integration(g.user["id"],key,config); session["mail_account"]=key
    except (ValueError,RuntimeError,OSError,imaplib.IMAP4.error,smtplib.SMTPException):
        flash("The account could not be connected. Check the server settings, app password, and TLS certificate. See the email setup guide.","error")
    else: flash("Email account connected. Open the inbox to load messages.","success")
    return redirect(url_for('integrations'))


@app.post('/integrations/email/disconnect')
def disconnect_email():
    key=request.form.get("account","")
    account=next((account for account in email_accounts(g.user) if account["key"]==key and account["key"]!="gmail"),None)
    if account is None: abort(404)
    prefix={"imap":"imap-","microsoft":"ms-","gmail":"gm-"}[account['kind']]+account["config"]["account_id"]+"-%"
    db=get_db(); db.execute("DELETE FROM gmail_cache WHERE user_id=? AND message_id LIKE ?",(g.user["id"],prefix))
    if account['kind']=='gmail':
        db.execute("DELETE FROM gmail_folder_pages WHERE user_id=? AND folder LIKE ?",(g.user['id'],gmail_folder_key(account,'')+'%'))
        db.execute("DELETE FROM gmail_account_counts WHERE user_id=? AND account_key=?",(g.user['id'],key))
    db.execute("DELETE FROM integrations WHERE user_id=? AND provider=?",(g.user["id"],key));db.commit()
    if session.get("mail_account")==key:session.pop("mail_account")
    flash("Email account disconnected and its local cache removed.","info")
    return redirect(url_for('integrations'))


@app.get('/auth/microsoft/callback')
def microsoft_callback():
    if session.pop("microsoft_connect_user",None)!=g.user["id"]:
        abort(400)
    try:
        token=microsoft.authorize_access_token()
        profile=graph_mail.request(token["access_token"],"GET","/me",params={"$select":"mail,userPrincipalName,displayName"})
        email=normalize_email(profile.get("mail") or profile.get("userPrincipalName", ""))
        if not valid_email(email):raise RuntimeError("Microsoft did not return an email address.")
        account_id=hashlib.sha256(email.encode()).hexdigest()[:12]
        key="email:microsoft:"+account_id
        save_integration(g.user["id"],key,{"kind":"microsoft","name":"Microsoft Outlook","email":email,"account_id":account_id,"token":token})
        session["mail_account"]=key
    except (OAuthError,requests.RequestException,ValueError,KeyError,RuntimeError):
        flash("Microsoft could not be connected. Check the OAuth setup and try again.","error")
    else: flash("Microsoft Outlook connected.","success")
    return redirect(url_for('integrations'))


@app.get('/integrations/teams/connect')
def teams_connect():
    if not app.config['MICROSOFT_CLIENT_ID'] or not app.config['MICROSOFT_CLIENT_SECRET']:
        flash('Microsoft Teams sign-in is not configured. See the Microsoft Teams setup guide.', 'error')
        return redirect(url_for('integrations'))
    callback_uri = app.config['MICROSOFT_TEAMS_REDIRECT_URI'] or url_for('teams_callback', _external=True)
    callback, origin = urlparse(callback_uri), urlparse(request.host_url)
    if callback.hostname in {'localhost', '127.0.0.1', '::1'} and origin.hostname in {'localhost', '127.0.0.1', '::1'} and callback.scheme == origin.scheme and callback.port == origin.port and callback.netloc != origin.netloc:
        return redirect(f'{callback.scheme}://{callback.netloc}{url_for("teams_connect")}')
    session['teams_connect_user'] = g.user['id']
    try:
        return teams_oauth.authorize_redirect(callback_uri, prompt='select_account')
    except (OAuthError, requests.RequestException, ValueError):
        session.pop('teams_connect_user', None)
        flash('Microsoft Teams sign-in could not start. Check the app registration and try again.', 'error')
        return redirect(url_for('integrations'))


@app.get('/auth/teams/callback')
def teams_callback():
    if session.pop('teams_connect_user', None) != g.user['id']: abort(400)
    try:
        token = teams_oauth.authorize_access_token()
        profile = graph_mail.request(token['access_token'], 'GET', '/me', params={'$select': 'id,displayName,mail,userPrincipalName'})
        graph_teams.segment(profile['id'])
        save_integration(g.user['id'], 'teams', {'stage': 'connected', 'token': token,
            'account': {'id': profile['id'], 'name': profile.get('displayName') or 'Microsoft Teams',
                'email': profile.get('mail') or profile.get('userPrincipalName') or ''}})
    except (OAuthError, requests.RequestException, ValueError, KeyError, TypeError, RuntimeError):
        flash('Microsoft Teams could not be connected. Check the app registration and organisation consent, then try again.', 'error')
    else:
        flash('Microsoft Teams connected. Open Apps to browse chats and team channels.', 'success')
    return redirect(url_for('integrations'))


@app.post('/integrations/teams/disconnect')
def teams_disconnect():
    delete_integration(g.user['id'], 'teams')
    flash('Microsoft Teams disconnected.', 'info')
    return redirect(url_for('integrations'))


def teams_api_result(operation):
    config = get_integration(g.user['id'], 'teams')
    if not config or config.get('stage') != 'connected': return jsonify(error='Connect Microsoft Teams first.'), 409
    try:
        token = microsoft_access_token({'key': 'teams', 'config': config})
        signer = URLSafeSerializer(app.config['SECRET_KEY'], salt='teams-conversations')
        return jsonify(operation(token, signer, g.user['id'], config['account']['id']))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except requests.HTTPError as error:
        code = error.response.status_code if error.response is not None else 502
        if code in {401,403}:
            return jsonify(error='Microsoft Teams denied access. Reconnect Teams and ask your administrator to approve the requested permissions.'), code
        if code == 404: return jsonify(error='This Teams conversation is no longer available. Refresh the list.'), 404
        return jsonify(error='Teams could not complete this request. Your draft is kept; check Teams before retrying a send.'), 502
    except (requests.RequestException, KeyError, TypeError, RuntimeError):
        app.logger.warning('Teams request failed for user id=%s', g.user['id'])
        return jsonify(error='Teams could not complete this request. Reconnect if access has expired. Your draft is kept; check Teams before retrying a send.'), 502


@app.get('/api/integrations/teams/conversations')
def teams_conversations():
    return teams_api_result(lambda token, signer, owner, account: graph_teams.conversations(token, signer, owner, account,
        kind=request.args.get('kind', 'chats'), team=request.args.get('team'), cursor=request.args.get('cursor')))


@app.route('/api/integrations/teams/conversations/<conversation>/messages', methods=['GET', 'POST'])
def teams_messages(conversation):
    reply = request.values.get('reply') or None
    text = request.form.get('text', '')
    if request.method == 'POST' and (not text.strip() or len(text.encode('utf-16-le')) // 2 > 4096):
        return jsonify(error='Enter a message of up to 4,096 characters.'), 400
    def operation(token, signer, owner, account):
        if request.method == 'POST':
            graph_teams.send(token, signer, owner, account, conversation, text, reply=reply)
            return {'sent': True}
        data = graph_teams.messages(token, signer, owner, account, conversation, cursor=request.args.get('cursor'), reply=reply)
        for message in data['messages']:
            if message.pop('html'): message['text'] = email_html_text(message['text'])
        return data
    return teams_api_result(operation)


@app.get('/api/integrations/<provider>/messages')
def integration_messages(provider):
    if provider not in {"telegram", "discord", "whatsapp"}:
        abort(404)
    config = get_integration(g.user["id"], provider)
    if config is None or (provider == "telegram" and config.get("stage") != "connected"):
        return jsonify(error="Connect this service first."), 409
    try:
        if provider == "telegram":
            _, messages = telegram_snapshot(config, g.user["id"], limit=50)
        elif provider == 'discord':
            messages = discord_recent_messages(config)
        else:
            messages = whatsapp_recent_messages(g.user['id'])
    except Exception as error:
        app.logger.warning("%s message preview failed for user id=%s", provider, g.user["id"])
        return jsonify(error=telegram_error_text(error) if provider == "telegram" else "Messages could not be loaded. Try again."), 502
    return jsonify(messages=messages)


@app.get('/integrations/google-chat/connect')
def google_chat_connect():
    return redirect(url_for('authenticate', provider='google', connect=1, service='chat'))


@app.post('/integrations/google-chat/disconnect')
def google_chat_disconnect():
    delete_integration(g.user['id'], 'google_chat')
    flash('Google Chat disconnected. Your Gmail connection is still available.', 'info')
    return redirect(url_for('integrations'))


def _google_chat_api(operation):
    try:
        config = get_integration(g.user['id'], 'google_chat')
        account = next((item for item in email_accounts(g.user) if config and item['key'] == config.get('account_key') and item['kind'] == 'gmail'), None)
        if not account: raise google_chat.ChatError('Connect Google Chat from Integrations first.', 409)
        stored = get_google_token(g.user) if account['key'] == 'gmail' else account['config']['token']
        if not set(google_chat.SCOPES.split()).issubset(set(stored.get('scope','').split())):
            raise google_chat.ChatError('Reconnect Google Chat and allow the requested permissions.', 409)
        token = get_gmail_access_token(g.user, account)
        if not token: raise google_chat.ChatError('Reconnect Google Chat to refresh your Google access.', 409)
        me = {'id':str((stored.get('userinfo') or {}).get('sub') or ''), 'email':account['email']}
        return operation(token, me, account['key'])
    except ValueError as error: return jsonify(error=str(error)), 400
    except google_chat.ChatError as error: return jsonify(error=str(error)), error.status
    except (requests.RequestException, KeyError, TypeError):
        app.logger.warning('Google Chat request failed for user id=%s', g.user['id'])
        return jsonify(error='Google Chat could not confirm the request. Your draft is kept; refresh before retrying.'), 502


def _google_chat_message_links(data, space_id):
    for message in [*data.get('messages', []), *data.get('updated_messages', []), *([data['message']] if data.get('message') else [])]:
        for attachment in message.get('attachments', []):
            if attachment.pop('downloadable', False):
                attachment['url'] = url_for('google_chat_attachment', space_id=space_id,
                    message_id=message['id'].split('/messages/')[1], attachment_index=attachment['index'])
    return data


@app.route('/api/integrations/google-chat/spaces', methods=['GET','POST'])
def google_chat_spaces():
    def operation(token, me, account):
        if request.method == 'GET': return jsonify(google_chat.spaces(token, me, request.args.get('cursor')))
        identity = request.form.get('request_id','')
        if not re.fullmatch(r'[0-9a-f]{32}', identity): raise ValueError('Retry creating the conversation from the form.')
        members = list(dict.fromkeys(normalize_email(value.strip()) for value in request.form.get('members','').split(',') if value.strip()))
        if any(not valid_email(email) or email == me['email'] for email in members): raise ValueError('Enter other participants’ email addresses, separated by commas.')
        return jsonify(conversation=google_chat.create_space(token, request.form.get('kind','DIRECT_MESSAGE'), request.form.get('title',''), members, identity))
    return _google_chat_api(operation)


@app.route('/api/integrations/google-chat/spaces/<space_id>/messages', methods=['GET','POST'])
def google_chat_messages(space_id):
    def operation(token, me, account):
        space = google_chat.resource('spaces/' + space_id)
        if request.method == 'GET':
            identifiers = request.args.get('known_ids','').split(',') if request.args.get('known_ids') else []
            if len(identifiers) > 50: raise ValueError('Too many Google Chat message identifiers.')
            names = [google_chat.resource(space + '/messages/' + identifier,'message',space) for identifier in identifiers]
            after, cursor = request.args.get('after') or None, None
            signer = URLSafeSerializer(app.config['SECRET_KEY'],salt='google-chat-page')
            if request.args.get('cursor'):
                try:
                    saved = signer.loads(request.args['cursor'])
                    if saved['owner'] != g.user['id'] or saved['account'] != account or saved['space'] != space: raise ValueError
                    after, cursor = saved['after'], saved['cursor']
                except (BadSignature,KeyError,TypeError,ValueError): raise ValueError('This Google Chat page is invalid or belongs to another conversation.') from None
            data = google_chat.messages(token, me, space, cursor, names, after)
            if data.get('next_cursor'): data['next_cursor'] = signer.dumps({'owner':g.user['id'],'account':account,'space':space,'after':after,'cursor':data['next_cursor']})
            data['incoming_page'] = bool(after)
            return jsonify(_google_chat_message_links(data, space_id))
        identity = request.form.get('request_id','')
        if not re.fullmatch(r'[0-9a-f]{32}',identity): raise ValueError('Retry sending from the message form.')
        attachment = None
        if request.form.get('attachment_token'):
            try:
                saved = URLSafeSerializer(app.config['SECRET_KEY'],salt='google-chat-attachment').loads(request.form['attachment_token'])
                if saved['owner'] != g.user['id'] or saved['account'] != account or saved['space'] != space or time.time() - saved['time'] > 3600: raise ValueError
                attachment = saved['ref']
            except (BadSignature, KeyError, TypeError, ValueError): raise ValueError('The attachment expired or belongs to another conversation. Select the file again.') from None
        sent = google_chat.send(token, space, request.form.get('text',''), identity, request.form.get('reply') or None, attachment)
        return jsonify(_google_chat_message_links({'message':google_chat.message_data(sent,me)},space_id))
    return _google_chat_api(operation)


@app.post('/api/integrations/google-chat/spaces/<space_id>/messages/<message_id>/actions')
def google_chat_action(space_id, message_id):
    def operation(token, me, account):
        name = google_chat.resource(f'spaces/{space_id}/messages/{message_id}','message')
        force = request.form.get('force','false')
        if force not in {'true','false'}: raise ValueError('Choose a valid deletion option.')
        data = google_chat.change_message(token, me, name, request.form.get('action',''), text=request.form.get('text',''),
            original=request.form.get('original'), force=force == 'true', emoji=request.form.get('emoji',''))
        return jsonify(_google_chat_message_links(data,space_id))
    return _google_chat_api(operation)


@app.post('/api/integrations/google-chat/spaces/<space_id>/attachments')
def google_chat_upload(space_id):
    def operation(token, me, account):
        space = google_chat.resource('spaces/' + space_id)
        file = request.files.get('file')
        if not file: raise ValueError('Choose a file to upload.')
        ref = google_chat.upload(token,space,file.filename,file.stream.read(google_chat.FILE_LIMIT + 1))
        signed = URLSafeSerializer(app.config['SECRET_KEY'],salt='google-chat-attachment').dumps({'owner':g.user['id'],'account':account,'space':space,'ref':ref,'time':time.time()})
        return jsonify(attachment_token=signed, name=secure_filename(file.filename) or 'attachment.bin')
    return _google_chat_api(operation)


@app.get('/api/integrations/google-chat/spaces/<space_id>/messages/<message_id>/attachments/<int:attachment_index>')
def google_chat_attachment(space_id, message_id, attachment_index):
    def operation(token, me, account):
        name = google_chat.resource(f'spaces/{space_id}/messages/{message_id}','message')
        message = google_chat.request(token,'GET',name)
        attachments = message.get('attachment',[])
        if not 0 <= attachment_index < len(attachments): raise ValueError('This attachment is no longer available.')
        attachment = attachments[attachment_index]
        resource = (attachment.get('attachmentDataRef') or {}).get('resourceName')
        if not resource: raise ValueError('Open this Google Drive attachment through Google Chat.')
        content = google_chat.download(token, resource)
        response = send_file(BytesIO(content),mimetype='application/octet-stream',as_attachment=True,download_name=secure_filename(attachment.get('contentName','')) or 'attachment.bin')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    return _google_chat_api(operation)


@app.route('/api/integrations/telegram/chats/<chat_id>', methods=['GET', 'POST'])
def telegram_chat_route(chat_id):
    if not re.fullmatch(r'-?[1-9][0-9]{0,15}', chat_id):
        return jsonify(error='Invalid Telegram conversation.'), 400
    config = get_integration(g.user['id'], 'telegram')
    if not config or config.get('stage') != 'connected':
        return jsonify(error='Connect Telegram first.'), 409
    topic_id = request.values.get('topic') or None
    before = request.args.get('before', '0')
    after = request.args.get('after', '0')
    if (topic_id is not None and not re.fullmatch(r'[1-9][0-9]{0,9}', topic_id)) or not re.fullmatch(r'[0-9]{1,10}', before) or not re.fullmatch(r'[0-9]{1,10}', after) or (int(before) and int(after)):
        return jsonify(error='Invalid topic or message cursor.'), 400
    text = request.form.get('text', '') if request.method == 'POST' else None
    request_id = request.form.get('request_id', '')
    reply_id = request.form.get('reply_id') or None
    known_ids = request.args.get('known_ids', '').split(',') if request.args.get('known_ids') else []
    if (reply_id and (not re.fullmatch(r'[1-9][0-9]{0,9}', reply_id) or int(reply_id) > 2147483647)) or len(known_ids) > 50 or any(not re.fullmatch(r'[1-9][0-9]{0,9}', value) or int(value) > 2147483647 for value in known_ids):
        return jsonify(error='Invalid Telegram message.'), 400
    if text is not None and (not text.strip() or len(text.encode('utf-16-le')) // 2 > 4096 or not re.fullmatch(r'[0-9a-f]{32}', request_id)):
        return jsonify(error='Enter a message of up to 4,096 characters and retry from the chat form.'), 400
    try:
        return jsonify(telegram_chat(config, g.user['id'], chat_id, topic_id=topic_id, topic_query=request.args.get('topic_search','').strip()[:100], before=int(before), after=int(after), text=text, request_id=request_id, reply_id=int(reply_id) if reply_id else None, known_ids=tuple(map(int, known_ids))))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except Exception as error:
        app.logger.warning('Telegram chat request failed for user id=%s', g.user['id'])
        message = telegram_error_text(error) if isinstance(error, RuntimeError) or (TELETHON_AVAILABLE and isinstance(error, FloodWaitError)) else 'Telegram could not complete the request. Your draft is kept; refresh before retrying.'
        return jsonify(error=message), 502


@app.post('/api/integrations/telegram/chats/<chat_id>/messages/<int:message_id>/actions')
def telegram_message_action_route(chat_id, message_id):
    action = request.form.get('action', '')
    topic = request.form.get('topic') or None
    target = request.form.get('destination') or None
    target_topic = request.form.get('destination_topic') or None
    text, emoji, identity = request.form.get('text', ''), request.form.get('emoji', ''), request.form.get('request_id', '')
    if not re.fullmatch(r'-?[1-9][0-9]{0,15}', chat_id) or not 1 <= message_id <= 2147483647 or action not in {'edit', 'delete', 'forward', 'pin', 'unpin', 'reaction'}:
        return jsonify(error='Invalid Telegram message action.'), 400
    if any(value and (not re.fullmatch(r'[1-9][0-9]{0,9}', value) or int(value) > 2147483647) for value in (topic, target_topic)):
        return jsonify(error='Invalid Telegram topic.'), 400
    if len(text.encode('utf-16-le')) // 2 > 4096 or len(emoji.encode('utf-16-le')) // 2 > 32 or any(ord(char) < 32 for char in emoji):
        return jsonify(error='The message or reaction is too long or invalid.'), 400
    if action == 'forward' and (not target or not re.fullmatch(r'-?[1-9][0-9]{0,15}', target) or not re.fullmatch(r'[0-9a-f]{32}', identity)):
        return jsonify(error='Choose a destination conversation and retry from the forwarding form.'), 400
    revoke = request.form.get('revoke', 'true')
    if revoke not in {'true', 'false'}: return jsonify(error='Choose a valid deletion option.'), 400
    config = get_integration(g.user['id'], 'telegram')
    if not config or config.get('stage') != 'connected': return jsonify(error='Connect Telegram first.'), 409
    try:
        return jsonify(telegram_message_action(config, g.user['id'], chat_id, message_id, action, text=text,
            topic_id=topic, original=request.form.get('original'), destination=target, destination_topic=target_topic,
            request_id=identity, emoji=emoji, revoke=revoke == 'true'))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except Exception as error:
        app.logger.warning('Telegram message action failed for user id=%s', g.user['id'])
        message = telegram_error_text(error) if isinstance(error, RuntimeError) or (TELETHON_AVAILABLE and isinstance(error, FloodWaitError)) else 'Telegram could not confirm this action. Your edit is kept; refresh the conversation before retrying.'
        return jsonify(error=message), 502


@app.get('/api/integrations/telegram/chats/<chat_id>/photo')
def telegram_photo_route(chat_id):
    if chat_id != 'me' and not re.fullmatch(r'-?[1-9][0-9]{0,15}', chat_id): abort(404)
    config = get_integration(g.user['id'], 'telegram')
    if not config or config.get('stage') != 'connected': abort(404)
    try:
        photo = telegram_photo(config, g.user['id'], chat_id)
    except Exception:
        return Response(status=404)
    if not isinstance(photo, bytes) or not photo.startswith(b'\xff\xd8\xff') or len(photo) > 2 * 1024 * 1024:
        return Response(status=404)
    return Response(photo, mimetype='image/jpeg', headers={'X-Content-Type-Options':'nosniff'})


@app.get('/api/integrations/telegram/chats/<chat_id>/messages/<int:message_id>/media')
def telegram_media_route(chat_id, message_id):
    if not re.fullmatch(r'-?[1-9][0-9]{0,15}', chat_id) or not 1 <= message_id <= 2147483647: abort(404)
    config = get_integration(g.user['id'], 'telegram')
    if not config or config.get('stage') != 'connected': abort(404)
    try:
        content, mime, filename = telegram_message_download(config, g.user['id'], chat_id, message_id)
    except ValueError as error:
        return jsonify(error=str(error)), 404
    except Exception:
        app.logger.warning('Telegram media request failed for user id=%s', g.user['id'])
        return jsonify(error='This media could not be loaded. Try again.'), 502
    response = send_file(BytesIO(content), mimetype=mime, conditional=True, etag=False,
        as_attachment=mime == 'application/octet-stream', download_name=filename)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.post('/integrations/telegram/start')
def telegram_start_route():
    api_id_text = request.form.get("api_id", "").strip()
    api_hash = request.form.get("api_hash", "").strip()
    phone = re.sub(r"[\s().-]", "", request.form.get("phone", ""))
    if not api_id_text.isdigit() or not 1 <= int(api_id_text) <= 2147483647:
        flash("Enter the numeric API ID from my.telegram.org.", "error")
        return redirect(url_for('integrations', app='telegram'))
    if not TELEGRAM_API_HASH_RE.fullmatch(api_hash):
        flash("Enter the 32-character API hash from my.telegram.org.", "error")
        return redirect(url_for('integrations', app='telegram'))
    if not TELEGRAM_PHONE_RE.fullmatch(phone):
        flash("Enter your phone number in international format, for example +233201234567.", "error")
        return redirect(url_for('integrations', app='telegram'))
    if not telegram_available():
        flash("Telegram account support is not installed. Run pip install telethon.", "error")
        return redirect(url_for('integrations', app='telegram'))
    try:
        telegram_send_code(g.user, int(api_id_text), api_hash, phone)
    except Exception as error:
        message = telegram_error_text(error)
        app.logger.warning("Telegram code request failed for user id=%s: %s", g.user["id"], message)
        flash(f"Telegram could not send a login code: {message}", "error")
    else:
        flash(
            "Login code sent. Open Telegram, find the message from Telegram, and enter the code here.",
            "success",
        )
    return redirect(url_for('integrations', app='telegram'))


@app.post('/integrations/telegram/verify')
def telegram_verify_route():
    code = re.sub(r"\s+", "", request.form.get("code", ""))
    if not code:
        flash("Enter the login code Telegram sent you.", "error")
        return redirect(url_for('integrations', app='telegram'))
    try:
        config = telegram_verify(g.user, code, "code")
    except Exception as error:
        message = telegram_error_text(error)
        app.logger.warning("Telegram code verification failed for user id=%s: %s", g.user["id"], message)
        flash(f"Telegram sign-in failed: {message}", "error")
    else:
        if config.get("stage") == "password":
            flash("Two-step verification is on. Enter your Telegram password.", "info")
        else:
            flash("Telegram account connected and saved on this device.", "success")
    return redirect(url_for('integrations', app='telegram'))


@app.post('/integrations/telegram/password')
def telegram_password_route():
    password = request.form.get("password", "")
    if not password:
        flash("Enter your Telegram two-step verification password.", "error")
        return redirect(url_for('integrations', app='telegram'))
    try:
        telegram_verify(g.user, password, "password")
    except Exception as error:
        message = telegram_error_text(error)
        app.logger.warning("Telegram password sign-in failed for user id=%s: %s", g.user["id"], message)
        flash(f"Telegram sign-in failed: {message}", "error")
    else:
        flash("Telegram account connected and saved on this device.", "success")
    return redirect(url_for('integrations', app='telegram'))


@app.post('/integrations/telegram/restart')
def telegram_restart_route():
    delete_integration(g.user["id"], "telegram")
    flash("Telegram sign-in restarted.", "info")
    return redirect(url_for('integrations', app='telegram'))


@app.post('/integrations/telegram/test')
def test_telegram_route():
    telegram = get_integration(g.user["id"], "telegram")
    if telegram is None or telegram.get("stage") != "connected":
        flash("Connect your Telegram account first.", "error")
        return redirect(url_for('integrations'))
    try:
        telegram_send_test(telegram, g.user["id"])
    except Exception as error:
        message = telegram_error_text(error)
        app.logger.warning("Telegram test failed for user id=%s: %s", g.user["id"], message)
        flash(f"Telegram test failed: {message}", "error")
    else:
        flash("Test message sent to your Telegram Saved Messages.", "success")
    return redirect(url_for('integrations'))


@app.post('/integrations/telegram/disconnect')
def disconnect_telegram_route():
    telegram = get_integration(g.user["id"], "telegram")
    telegram_disconnect(telegram, g.user["id"])
    delete_integration(g.user["id"], "telegram")
    flash("Telegram has been disconnected.", "info")
    return redirect(url_for('integrations'))


@app.post('/integrations/whatsapp')
def connect_whatsapp_route():
    phone_number_id = re.sub(r"\D", "", request.form.get("phone_number_id", ""))
    access_token = request.form.get("access_token", "").strip()
    if access_token.lower().startswith("bearer "):
        access_token = access_token[7:].strip()
    verify_token = request.form.get("verify_token", "").strip()
    if not phone_number_id:
        flash("Enter the WhatsApp phone number ID from the Meta developer dashboard.", "error")
        return redirect(url_for('integrations', app='whatsapp'))
    if not access_token or len(access_token) > 4096:
        flash("Enter a valid WhatsApp Cloud API access token.", "error")
        return redirect(url_for('integrations', app='whatsapp'))
    if verify_token and not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", verify_token):
        flash("The webhook verify token must be 8-64 letters, numbers, underscores or dashes.", "error")
        return redirect(url_for('integrations', app='whatsapp'))
    try:
        connect_whatsapp(g.user, phone_number_id, access_token, verify_token)
    except requests.RequestException:
        app.logger.warning("WhatsApp connection failed for user id=%s: network error", g.user["id"])
        flash("WhatsApp could not be reached. Check your connection and try again.", "error")
    except RuntimeError as error:
        app.logger.warning("WhatsApp connection failed for user id=%s: %s", g.user["id"], error)
        flash(f"WhatsApp could not be connected: {error}", "error")
    else:
        flash("WhatsApp is connected and saved on this device.", "success")
    return redirect(url_for('integrations', app='whatsapp'))


@app.post('/integrations/whatsapp/test')
def test_whatsapp_route():
    whatsapp = get_integration(g.user["id"], "whatsapp")
    if whatsapp is None:
        flash("Connect WhatsApp first.", "error")
        return redirect(url_for('integrations'))
    recipient = re.sub(r"\D", "", request.form.get("recipient", ""))
    text = request.form.get("message", "").strip()[:4096]
    if not 7 <= len(recipient) <= 15:
        flash("Enter the recipient's phone number with country code.", "error")
        return redirect(url_for('integrations'))
    try:
        whatsapp_send_message(
            whatsapp,
            recipient,
            text or "CentroMail connection test: your WhatsApp integration is working.",
        )
    except requests.RequestException:
        app.logger.warning("WhatsApp test failed for user id=%s: network error", g.user["id"])
        flash("WhatsApp could not be reached. Check your connection and try again.", "error")
    except RuntimeError as error:
        app.logger.warning("WhatsApp test failed for user id=%s: %s", g.user["id"], error)
        flash(f"WhatsApp test failed: {error}", "error")
    else:
        flash("Test message sent through WhatsApp.", "success")
    return redirect(url_for('integrations'))


@app.post('/integrations/whatsapp/disconnect')
def disconnect_whatsapp_route():
    delete_integration(g.user["id"], "whatsapp")
    get_db().execute("DELETE FROM whatsapp_messages WHERE user_id = ?", (g.user["id"],))
    get_db().commit()
    flash("WhatsApp has been disconnected.", "info")
    return redirect(url_for('integrations'))


@app.route('/integrations/whatsapp/webhook', methods=['GET', 'POST'])
def whatsapp_webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge", "")
        user_id, _ = find_whatsapp_integration(verify_token=token) if token else (None, None)
        if mode == "subscribe" and user_id is not None:
            return challenge, 200, {"Content-Type": "text/plain"}
        abort(403)

    secret = app.config.get("WHATSAPP_APP_SECRET")
    if not secret:
        abort(503, description="WhatsApp webhook verification is not configured.")
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), request.get_data(), hashlib.sha256).hexdigest()
    if not re.fullmatch(r'sha256=[a-f0-9]{64}',signature) or not hmac.compare_digest(expected, signature):
        abort(403)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        abort(400)
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            metadata = value.get("metadata", {}) or {}
            user_id, _ = find_whatsapp_integration(
                phone_number_id=str(metadata.get("phone_number_id", ""))
            )
            if user_id is None:
                continue
            for message in value.get("messages", []) or []:
                try:
                    store_whatsapp_message(user_id, message)
                except Exception:
                    app.logger.exception("Could not store a WhatsApp webhook message")
    return "ok", 200, {"Content-Type": "text/plain"}


@app.post('/integrations/discord')
def connect_discord_route():
    bot_token = request.form.get("bot_token", "").strip()
    if bot_token.lower().startswith("bot "):
        bot_token = bot_token[4:].strip()
    channel_id = re.sub(r"\D", "", request.form.get("channel_id", ""))
    if not DISCORD_TOKEN_RE.fullmatch(bot_token):
        flash("Enter a valid Discord bot token from the Bot settings page.", "error")
        return redirect(url_for('integrations', app='discord'))
    if not 15 <= len(channel_id) <= 25:
        flash("Enter the numeric Discord channel ID.", "error")
        return redirect(url_for('integrations', app='discord'))
    try:
        connect_discord(g.user, bot_token, channel_id)
    except requests.RequestException:
        app.logger.warning("Discord connection failed for user id=%s: network error", g.user["id"])
        flash("Discord could not be reached. Check your connection and try again.", "error")
    except RuntimeError as error:
        app.logger.warning("Discord connection failed for user id=%s: %s", g.user["id"], error)
        flash(f"Discord could not be connected: {error}", "error")
    else:
        flash("Discord is connected and saved on this device.", "success")
    return redirect(url_for('integrations', app='discord'))


@app.post('/integrations/discord/test')
def test_discord_route():
    discord = get_integration(g.user["id"], "discord")
    if discord is None:
        flash("Connect Discord first.", "error")
        return redirect(url_for('integrations'))
    text = request.form.get("message", "").strip()[:2000]
    try:
        discord_send_message(
            discord,
            text or "CentroMail connection test: your Discord integration is working.",
        )
    except requests.RequestException:
        app.logger.warning("Discord test failed for user id=%s: network error", g.user["id"])
        flash("Discord could not be reached. Check your connection and try again.", "error")
    except RuntimeError as error:
        app.logger.warning("Discord test failed for user id=%s: %s", g.user["id"], error)
        flash(f"Discord test failed: {error}", "error")
    else:
        flash("Test message sent to the Discord channel.", "success")
    return redirect(url_for('integrations'))


@app.post('/integrations/discord/disconnect')
def disconnect_discord_route():
    delete_integration(g.user["id"], "discord")
    flash("Discord has been disconnected.", "info")
    return redirect(url_for('integrations'))


@app.post('/integrations/social/<provider>/connect')
def connect_social_route(provider):
    spec = SOCIAL_PROVIDERS_BY_KEY.get(provider)
    if spec is None:
        abort(404)
    if provider in integration_catalog.PLACEHOLDER_PROVIDERS:
        abort(409, description=spec['name'] + ' is coming soon.')
    values = {
        field["name"]: request.form.get(field["name"], "")
        for field in spec["fields"]
    }
    try:
        config = social_connect(provider, values)
        save_integration(g.user["id"], "social:" + provider, config)
    except RuntimeError as error:
        app.logger.warning(
            "%s connection failed for user id=%s: %s",
            spec["name"],
            g.user["id"],
            error,
        )
        flash(f"{spec['name']} could not be connected: {error}", "error")
    except requests.RequestException:
        app.logger.warning(
            "%s connection failed for user id=%s: network error",
            spec["name"],
            g.user["id"],
        )
        flash(
            f"{spec['name']} could not be reached. Check your connection and try again.",
            "error",
        )
    else:
        flash(f"{spec['name']} is connected and saved on this device.", "success")
    return redirect(url_for('integrations', app=provider))


@app.post('/integrations/social/<provider>/test')
def test_social_route(provider):
    spec = SOCIAL_PROVIDERS_BY_KEY.get(provider)
    if spec is None:
        abort(404)
    if provider in integration_catalog.PLACEHOLDER_PROVIDERS:
        abort(409, description=spec['name'] + ' is coming soon.')
    config = get_integration(g.user["id"], "social:" + provider)
    if config is None:
        flash(f"Connect {spec['name']} first.", "error")
        return redirect(url_for('integrations'))
    text = request.form.get("message", "").strip()
    text = text or f"CentroMail test: your {spec['name']} integration is working."
    text = text[: spec.get("max_length", 5000)]
    try:
        social_publish(provider, config, text)
    except RuntimeError as error:
        app.logger.warning(
            "%s test failed for user id=%s: %s", spec["name"], g.user["id"], error
        )
        flash(f"{spec['name']} test failed: {error}", "error")
    except requests.RequestException:
        app.logger.warning(
            "%s test failed for user id=%s: network error", spec["name"], g.user["id"]
        )
        flash(
            f"{spec['name']} could not be reached. Check your connection and try again.",
            "error",
        )
    else:
        flash(f"Test post sent to {spec['name']}.", "success")
    return redirect(url_for('integrations'))


@app.post('/integrations/social/<provider>/disconnect')
def disconnect_social_route(provider):
    spec = SOCIAL_PROVIDERS_BY_KEY.get(provider)
    if spec is None:
        abort(404)
    delete_integration(g.user["id"], "social:" + provider)
    flash(f"{spec['name']} has been disconnected.", "info")
    return redirect(url_for('integrations'))


@app.post('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.get('/auth/<provider>')
def authenticate(provider):
    if provider not in {'google', 'microsoft'}:
        abort(404)
    if provider == "google":
        if request.args.get('connect')=='1' and g.user is None:
            flash("Sign in to CentroMail first, then add Gmail from Integrations.","info")
            return redirect(url_for('login'))
        if not app.config["GOOGLE_CLIENT_ID"] or not app.config["GOOGLE_CLIENT_SECRET"]:
            flash("Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", "error")
            return redirect(url_for('login'))
        callback_uri = google_callback_uri()
        callback = urlparse(callback_uri)
        origin = urlparse(request.host_url)
        loopback = {"localhost", "127.0.0.1", "::1"}
        # OAuth state is stored in a host-specific cookie. Start sign-in on
        # the configured local callback host before creating that state.
        if (callback.hostname in loopback and origin.hostname in loopback
                and callback.scheme == origin.scheme and callback.port == origin.port
                and callback.netloc != origin.netloc):
            options = {}
            if request.args.get('connect') == '1':
                options['connect'] = 1
            if request.args.get('cleanup') == '1':
                options['cleanup'] = 1
                if request.args.get('account'):
                    options['account'] = request.args['account']
            if request.args.get('service') == 'chat':
                options['service'] = 'chat'
            path = url_for('authenticate', provider='google', **options) if g.user is not None or request.args.get('connect') == '1' else url_for('authenticate', provider='google')
            return redirect(f"{callback.scheme}://{callback.netloc}{path}")
        if g.user is not None:
            session['google_connect_user']=g.user['id']
            session['google_connect_chat'] = request.args.get('service') == 'chat'
            session['google_cleanup_return'] = request.args.get('cleanup') == '1'
            session['google_cleanup_account'] = request.args.get('account', '')
        try:
            if g.user is not None:
                options = {'prompt':'select_account consent','access_type':'offline','include_granted_scopes':'true'}
                if session.get('google_connect_chat'):
                    options['scope'] = google.client_kwargs['scope'] + ' ' + google_chat.SCOPES
                return google.authorize_redirect(callback_uri, **options)
            return google.authorize_redirect(callback_uri)
        except (requests.RequestException, OAuthError, ValueError):
            session.pop('google_connect_user',None)
            session.pop('google_connect_chat',None)
            flash("Could not connect to Google. Please try signing in again.", "error")
            return redirect(url_for('login'))

    if g.user is None:
        flash("Sign in to CentroMail first, then connect Outlook from Integrations.", "info")
        return redirect(url_for('login'))
    if not app.config["MICROSOFT_CLIENT_ID"] or not app.config["MICROSOFT_CLIENT_SECRET"]:
        flash("Microsoft needs an OAuth app. Follow docs/email-provider-setup.md to configure it.","info")
        return redirect(url_for('integrations'))
    callback_uri=app.config["MICROSOFT_REDIRECT_URI"] or url_for('microsoft_callback',_external=True)
    origin=urlparse(request.host_url); callback=urlparse(callback_uri)
    if origin.hostname in {"localhost","127.0.0.1","::1"} and callback.hostname in {"localhost","127.0.0.1","::1"} and origin.netloc!=callback.netloc:
        return redirect(f"{callback.scheme}://{callback.netloc}{url_for('authenticate',provider='microsoft')}")
    session["microsoft_connect_user"]=g.user["id"]
    try:return microsoft.authorize_redirect(callback_uri)
    except (OAuthError,requests.RequestException,ValueError):
        session.pop("microsoft_connect_user",None)
        flash("Microsoft sign-in could not be started. Check the OAuth setup.","error")
        return redirect(url_for('integrations'))



@app.get('/auth/google/callback')
def google_callback():
    connect_user = session.pop('google_connect_user', None)
    connect_chat = session.pop('google_connect_chat', False)
    cleanup_return = session.pop('google_cleanup_return', False)
    cleanup_account = session.pop('google_cleanup_account', '')
    cleanup_url = url_for('cleanup', account=cleanup_account, resume=1) if cleanup_return else url_for('login')
    if connect_user is not None and (g.user is None or g.user['id'] != connect_user):
        abort(400, description="Sign in to the account that started this Gmail connection.")
    if not app.config["GOOGLE_CLIENT_ID"] or not app.config["GOOGLE_CLIENT_SECRET"]:
        flash("Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", "error")
        return redirect(url_for('login'))

    if request.args.get("error"):
        flash("Google sign-in was cancelled or denied. Please try again.", "error")
        return redirect(cleanup_url)

    try:
        token = google.authorize_access_token()
    except OAuthError as error:
        if error.error == "invalid_grant":
            message = "Google rejected the authorization code. Start sign-in again and use the same browser address."
        else:
            message = "Google sign-in could not be completed. Check the OAuth callback URI and try again."
        flash(message, "error")
        return redirect(cleanup_url)
    except (requests.RequestException, ValueError):
        flash("Google sign-in took too long or could not connect. Please try again.", "error")
        return redirect(cleanup_url)

    profile = token.get("userinfo")
    if not profile or profile.get("email_verified") is not True:
        flash("Google did not provide a verified email address.", "error")
        return redirect(url_for('onboarding'))

    email = normalize_email(profile.get("email", ""))
    if not valid_email(email):
        flash("Google did not provide a valid email address.", "error")
        return redirect(url_for('onboarding'))

    if connect_user is not None:
        if email == g.user['email']:
            previous = get_google_token(g.user) or {}
            if not token.get('refresh_token'):
                token['refresh_token'] = previous.get('refresh_token')
            store_google_token(g.user['id'], token)
            key = 'gmail'
        else:
            account_id = hashlib.sha256(email.encode()).hexdigest()[:12]
            key = 'email:gmail:' + account_id
            previous = get_integration(g.user['id'], key) or {}
            if not token.get('refresh_token'):
                token['refresh_token'] = previous.get('token',{}).get('refresh_token')
            save_integration(g.user['id'], key, {'kind':'gmail','name':'Gmail','email':email,'account_id':account_id,'token':token})
        session['mail_account'] = key
        if connect_chat:
            if set(google_chat.SCOPES.split()).issubset(set(token.get('scope','').split())):
                save_integration(g.user['id'], 'google_chat', {'account_key':key})
                flash(f'Google Chat connected: {email}.', 'success')
                return redirect(url_for('inbox') + '#apps')
            flash('Google Chat permission was not granted. Reconnect Google Chat and allow the requested access.', 'error')
        flash(f"Gmail connected: {email}.", 'success')
        if cleanup_return:
            return redirect(url_for('cleanup', account=key, resume=1))
        return redirect(url_for('inbox', account=key))

    user = find_user(email)
    avatar_url = profile.get("picture")
    if not isinstance(avatar_url, str) or not avatar_url.startswith("https://"):
        avatar_url = None
    if user is None:
        name = (profile.get("name") or email.split("@", 1)[0]).strip()[:100]
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name, email, password, avatar_url) VALUES (?, ?, ?, ?)",
                (name or email, email, generate_password_hash(secrets.token_urlsafe(32)), avatar_url),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
        user = find_user(email)
    if user is None:
        abort(500, description="Could not create or find the Google account.")
    elif avatar_url and user["avatar_url"] != avatar_url:
        get_db().execute(
            "UPDATE users SET avatar_url = ? WHERE id = ?",
            (avatar_url, user["id"]),
        )
        get_db().commit()
        user = find_user(email)

    previous_token = get_google_token(user)
    if previous_token and not token.get("refresh_token"):
        token["refresh_token"] = previous_token.get("refresh_token")
    store_google_token(user["id"], token)
    sign_in(user)
    return redirect(url_for('dashboard'))

@app.get("/cleanup")
def cleanup():
    account = active_email_account(g.user)
    return render_template(
        "cleanup.html",
        account=account,
        mail_accounts=email_accounts(g.user),
    )


@app.get("/api/cleanup/promotions")
def cleanup_promotions():
    account = active_email_account(g.user)

    if account["kind"] != "gmail":
        return jsonify(error="Promotional email scanning currently supports Gmail only."), 400

    try:
        token = get_gmail_access_token(g.user, account)
    except requests.HTTPError:
        return jsonify(error="Reconnect Gmail to scan promotional emails.", reconnect=True), 401
    except requests.RequestException:
        return jsonify(error="Could not connect to Gmail. Please try again."), 502

    if not token:
        return jsonify(error="Reconnect Gmail to scan promotional emails.", reconnect=True), 401

    try:
        message_ids = scan_promotions(token)
        raw_ids = [item["id"] for item in message_ids]
        if any(not isinstance(message_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", message_id) for message_id in raw_ids):
            raise ValueError("Gmail returned an invalid message identifier")
        return jsonify(count=len(raw_ids), message_ids=[gmail_message_key(account, raw_id) for raw_id in raw_ids])
    except requests.HTTPError as error:
        return gmail_cleanup_http_error(error, "the promotional email scan")
    except (requests.RequestException, ValueError):
        return jsonify(error="Could not scan promotional emails. Please try again."), 502


@app.get("/api/cleanup/promotions/details")
def cleanup_promotion_details():
    account = active_email_account(g.user)
    if account["kind"] != "gmail":
        return jsonify(error="Promotional email scanning currently supports Gmail only."), 400

    identifiers = request.args.getlist("message_ids")
    if not identifiers or len(identifiers) > 50 or len(set(identifiers)) != len(identifiers):
        return jsonify(error="Provide between 1 and 50 unique message IDs."), 400

    try:
        raw_ids = [gmail_raw_message_id(account, identifier) for identifier in identifiers]
    except ValueError:
        return jsonify(error="One or more message IDs do not belong to this Gmail account."), 400

    try:
        token = get_gmail_access_token(g.user, account)
    except requests.HTTPError as error:
        if gmail_error_status(error) in {401, 403}:
            return jsonify(error="Reconnect Gmail to continue scanning.", reconnect=True), 401
        return jsonify(error="Could not connect to Gmail. Please try again."), 502
    except requests.RequestException:
        return jsonify(error="Could not connect to Gmail. Please try again."), 502
    if not token:
        return jsonify(error="Reconnect Gmail to continue scanning.", reconnect=True), 401

    headers = {"Authorization": "Bearer " + token}
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            details = list(executor.map(
                lambda message_id: fetch_cleanup_gmail_detail(headers, message_id),
                raw_ids,
            ))
        messages = [
            {
                "id": gmail_message_key(account, message["id"]),
                "sender": message["sender"],
                "subject": message["subject"],
                "date": message["date"],
                "preview": message["preview"],
            }
            for message in details
            if "CATEGORY_PROMOTIONS" in message.get("label_ids", [])
            and not {"TRASH", "SPAM", "STARRED", "IMPORTANT"}.intersection(message.get("label_ids", []))
        ]
        return jsonify(checked=len(raw_ids), messages=messages)
    except requests.HTTPError as error:
        return gmail_cleanup_http_error(error, "checking promotional messages")
    except requests.RequestException:
        return jsonify(error="Could not check promotional emails. Please try again."), 502


@app.post("/api/cleanup/gmail/refresh")
def cleanup_gmail_refresh():
    account = active_email_account(g.user)
    if account["kind"] != "gmail":
        return jsonify(error="Promotional email scanning currently supports Gmail only."), 400
    try:
        token = get_gmail_access_token(g.user, account, force_refresh=True)
    except requests.RequestException:
        return jsonify(error="Could not reconnect to Gmail. Please try again.", reconnect=True), 502
    if not token:
        return jsonify(error="Gmail could not refresh access. Reconnect the account to continue.", reconnect=True), 401
    return jsonify(reconnected=True)


@app.post("/api/cleanup/promotions/trash")
def cleanup_trash_promotions():
    account = active_email_account(g.user)
    if account["kind"] != "gmail":
        return jsonify(error="Promotional email cleanup currently supports Gmail only."), 400

    identifiers = list(dict.fromkeys(request.form.getlist("message_ids")))
    if not identifiers or len(identifiers) > 500:
        return jsonify(error="Select between 1 and 500 promotional emails."), 400
    try:
        raw_ids = [gmail_raw_message_id(account, identifier) for identifier in identifiers]
    except ValueError:
        return jsonify(error="One or more message IDs do not belong to this Gmail account."), 400

    try:
        token = get_gmail_access_token(g.user, account)
        if not token:
            return jsonify(error="Gmail access expired.", refresh_required=True), 401
        headers = {"Authorization": "Bearer " + token}
        with ThreadPoolExecutor(max_workers=4) as executor:
            details = list(executor.map(
                lambda message_id: fetch_cleanup_gmail_detail(headers, message_id),
                raw_ids,
            ))
        trash_ids = [
            message["id"] for message in details
            if "CATEGORY_PROMOTIONS" in message.get("label_ids", [])
            and not {"TRASH", "SPAM", "STARRED", "IMPORTANT"}.intersection(message.get("label_ids", []))
        ]
        if not trash_ids:
            return jsonify(trashed=0, skipped=len(identifiers), ids=[])

        response = google_requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/batchModify",
            headers={"Authorization": "Bearer " + token},
            json={"ids": trash_ids, "addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]},
            timeout=(5, 20),
        )
        response.raise_for_status()

        db = get_db()
        db.executemany(
            "DELETE FROM gmail_cache WHERE user_id=? AND message_id=?",
            [(g.user["id"], gmail_message_key(account, raw_id)) for raw_id in trash_ids],
        )
        if account["key"] == "gmail":
            db.execute("DELETE FROM gmail_folder_pages WHERE user_id=? AND folder NOT LIKE 'gm:%'", (g.user["id"],))
            db.execute("DELETE FROM gmail_mailbox_counts WHERE user_id=?", (g.user["id"],))
            db.execute("DELETE FROM gmail_sync_state WHERE user_id=?", (g.user["id"],))
        else:
            db.execute(
                "DELETE FROM gmail_folder_pages WHERE user_id=? AND folder LIKE ?",
                (g.user["id"], gmail_folder_key(account, "") + "%"),
            )
            db.execute(
                "DELETE FROM gmail_account_counts WHERE user_id=? AND account_key=?",
                (g.user["id"], account["key"]),
            )
        db.commit()
        return jsonify(
            trashed=len(trash_ids),
            skipped=len(identifiers) - len(trash_ids),
            ids=[gmail_message_key(account, raw_id) for raw_id in trash_ids],
        )
    except requests.HTTPError as error:
        if gmail_error_status(error) == 401:
            return jsonify(error="Gmail access expired.", refresh_required=True), 401
        return gmail_cleanup_http_error(error, "moving promotional messages to Trash")
    except requests.RequestException:
        return jsonify(error="Could not move promotional emails to Trash. Please try again."), 502


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
