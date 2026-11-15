import os
import asyncio
import json
import base64
import html
import logging
import re
import secrets
import sqlite3
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import bleach
import tinycss2
from bleach.css_sanitizer import CSSSanitizer
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,
                   session, url_for)
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from telethon import TelegramClient
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
    GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID"),
    GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET"),
    GOOGLE_REDIRECT_URI=os.environ.get("GOOGLE_REDIRECT_URI"),
)
oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile https://www.googleapis.com/auth/gmail.modify"},
    authorize_params={"access_type": "offline", "prompt": "consent"},
)


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
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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


with app.app_context():
    init_db()


def normalize_email(email):
    return email.strip().lower()


def valid_email(email):
    return len(email) <= 254 and EMAIL_RE.fullmatch(email) is not None


def find_user(email):
    return get_db().execute(
        "SELECT * FROM users WHERE lower(email) = ?", (normalize_email(email),)
    ).fetchone()


@app.template_global()
def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


PROTECTED_ENDPOINTS = {
    "home", "dashboard", "inbox", "mail", "message_detail", "compose", "settings",
    "mailbox_messages", "mailbox_counts", "mail_action",
    "delete_account",
    "integrations", "telegram_start_route", "telegram_verify_route",
    "telegram_password_route", "telegram_restart_route", "test_telegram_route",
    "disconnect_telegram_route", "connect_whatsapp_route", "test_whatsapp_route",
    "disconnect_whatsapp_route", "connect_discord_route", "test_discord_route",
    "disconnect_discord_route", "connect_social_route", "test_social_route",
    "disconnect_social_route",
}


@app.before_request
def load_user_and_check_forms():
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


def render_auth(active_panel="login", email="", name="", remember=False):
    return render_template(
        "register.html" if active_panel == "signup" else "login.html",
        email=email, name=name, remember=remember,
    )


def make_stats(messages):
    return {
        'total': len(messages),
        'unread': sum(1 for message in messages if message['unread']),
        'starred': sum(1 for message in messages if message['starred']),
        'sent': 12,
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


def get_gmail_access_token(user):
    token = get_google_token(user)
    if not token:
        return None
    expires_at = token.get("expires_at", 0)
    if token.get("access_token") and expires_at > datetime.now(timezone.utc).timestamp() + 60:
        return token["access_token"]
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        return None
    response = requests.post(
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
    store_google_token(user["id"], token)
    return token["access_token"]


GMAIL_METADATA_TTL = 12 * 60 * 60
GMAIL_BODY_TTL = 24 * 60 * 60


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
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", "\n".join(html_parts))
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</p\s*>|</div\s*>|</tr\s*>", "\n", text)
        plain_text = html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()
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
                "*": ["class", "style", "id"]
            },
            protocols=["http", "https", "mailto"],
            css_sanitizer=email_css,
            strip=True
        ).strip()
        if styles:
            safe_html = "<style>" + styles.replace("<", "\\3c ") + "</style>" + safe_html

    return {"text": plain_text, "html": safe_html}


def gmail_metadata_from_payload(payload, fallback_id):
    message_headers = payload.get("payload", {}).get("headers", [])
    label_ids = set(payload.get("labelIds", []))
    sender = gmail_header(message_headers, "From")
    return {
        "id": payload.get("id", fallback_id),
        "sender": gmail_sender(sender),
        "email": gmail_sender_email(sender),
        "subject": gmail_header(message_headers, "Subject") or "(No subject)",
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
GMAIL_BATCH_SIZE = 50
_gmail_sync_locks = {}
_gmail_sync_locks_guard = threading.Lock()


def _gmail_sync_lock(user_id):
    with _gmail_sync_locks_guard:
        return _gmail_sync_locks.setdefault(user_id, threading.Lock())


def load_gmail_message_ids(user_id):
    row = get_db().execute(
        "SELECT message_ids, listed_at FROM gmail_sync_state WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None or time.time() - row["listed_at"] > GMAIL_LIST_TTL:
        return None
    try:
        message_ids = json.loads(row["message_ids"])
    except (TypeError, json.JSONDecodeError):
        return None
    return message_ids if isinstance(message_ids, list) else None


def save_gmail_message_ids(user_id, message_ids):
    get_db().execute(
        """INSERT INTO gmail_sync_state (user_id, message_ids, listed_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               message_ids = excluded.message_ids,
               listed_at = excluded.listed_at""",
        (user_id, json.dumps(message_ids), time.time()),
    )
    get_db().commit()


def fetch_gmail_message_ids(user, headers):
    message_ids = []
    next_page_token = None
    while True:
        params = {
            "userId": "me",
            "labelIds": "INBOX",
            "maxResults": 100,
            "includeSpamTrash": "false",
        }
        if next_page_token:
            params["pageToken"] = next_page_token
        response = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params=params,
            timeout=(5, 15),
        )
        response.raise_for_status()
        page = response.json()
        message_ids.extend(item["id"] for item in page.get("messages", []) if item.get("id"))
        next_page_token = page.get("nextPageToken")
        if not next_page_token:
            return message_ids


def _fetch_gmail_detail(headers, message_id):
    detail = requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
        headers=headers,
        params=[
            ("userId", "me"),
            ("format", "metadata"),
            ("metadataHeaders", "From"),
            ("metadataHeaders", "Subject"),
            ("metadataHeaders", "Date"),
        ],
        timeout=(5, 15),
    )
    detail.raise_for_status()
    return gmail_metadata_from_payload(detail.json(), message_id)


def sync_gmail_inbox(user, batch_size=GMAIL_BATCH_SIZE, force_refresh=False):
    """Load a bounded batch and let the page continue the sync.

    A large inbox cannot be fetched in one request: Gmail's per-user quota
    rejects thousands of metadata requests in a burst.  Each call therefore
    lists the inbox (cached for five minutes unless manually refreshed),
    fills at most ``batch_size`` missing messages, and reports how many are
    left.  The inbox page reloads itself until ``remaining`` reaches zero.
    """
    result = {
        "messages": load_cached_gmail_messages(user),
        "total": None,
        "remaining": None,
        "busy": False,
        "error": None,
        "retry_after": 0,
    }
    access_token = get_gmail_access_token(user)
    if not access_token:
        result["error"] = "no_token"
        return result

    lock = _gmail_sync_lock(user["id"])
    if not lock.acquire(blocking=False):
        result["busy"] = True
        result["retry_after"] = 3
        return result
    try:
        headers = {"Authorization": "Bearer " + access_token}
        message_ids = None if force_refresh else load_gmail_message_ids(user["id"])
        if message_ids is None:
            message_ids = fetch_gmail_message_ids(user, headers)
            save_gmail_message_ids(user["id"], message_ids)

        messages_by_id = {}
        missing_ids = []
        for message_id in message_ids:
            cached = gmail_cache_get(user["id"], message_id)
            if cached is not None:
                messages_by_id[message_id] = cached
            else:
                missing_ids.append(message_id)

        batch = missing_ids[:batch_size]
        errors = []
        dropped_ids = set()
        fetched = 0
        if batch:
            executor = ThreadPoolExecutor(max_workers=3)
            futures = {
                executor.submit(_fetch_gmail_detail, headers, message_id): message_id
                for message_id in batch
            }
            try:
                for future in as_completed(futures):
                    message_id = futures[future]
                    try:
                        metadata = future.result()
                    except CancelledError:
                        continue
                    except (requests.RequestException, KeyError, ValueError) as error:
                        if gmail_error_status(error) in (404, 410):
                            # The message was deleted between listing and
                            # fetching; stop retrying it forever.
                            dropped_ids.add(message_id)
                            app.logger.info(
                                "Dropping deleted Gmail message %s for user id=%s",
                                message_id,
                                user["id"],
                            )
                            continue
                        errors.append(error)
                        if "quota" in gmail_error_reason(error):
                            # Stop the round instead of burning the remaining
                            # quota on requests Google will reject anyway.
                            for pending in futures:
                                pending.cancel()
                            break
                    else:
                        gmail_cache_put(user["id"], message_id, metadata=metadata)
                        messages_by_id[message_id] = metadata
                        fetched += 1
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        if dropped_ids:
            message_ids = [item for item in message_ids if item not in dropped_ids]
            save_gmail_message_ids(user["id"], message_ids)
        remaining = len(missing_ids) - fetched - len(dropped_ids)
        result["messages"] = [
            messages_by_id[message_id]
            for message_id in message_ids
            if message_id in messages_by_id
        ]
        result["total"] = len(message_ids)
        result["remaining"] = remaining
        if errors:
            result["error"] = gmail_error_message(errors[0])
            result["retry_after"] = 60
            app.logger.warning(
                "Gmail sync paused for user id=%s: loaded=%s remaining=%s reason=%s",
                user["id"],
                len(messages_by_id),
                remaining,
                gmail_error_reason(errors[0]) or errors[0],
            )
        else:
            app.logger.info(
                "Gmail sync for user id=%s: total=%s loaded=%s remaining=%s",
                user["id"],
                len(message_ids),
                len(messages_by_id),
                remaining,
            )
        return result
    finally:
        lock.release()


def fetch_gmail_messages(user):
    """Compatibility wrapper used by callers that need the cached inbox."""
    return sync_gmail_inbox(user, batch_size=10 ** 9)["messages"]


def fetch_gmail_message(user, message_id):
    """Fetch and decode one complete Gmail message for the detail view."""
    metadata = gmail_cache_get(user["id"], message_id)
    body = gmail_cache_get(user["id"], message_id, body=True)
    if metadata is not None and body is not None:
        return {**metadata, "date": gmail_message_date(metadata), "body": body}

    access_token = get_gmail_access_token(user)
    if not access_token:
        return None
    response = requests.get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
        headers={"Authorization": "Bearer " + access_token},
        params={"userId": "me", "format": "full"},
        timeout=(5, 20),
    )
    response.raise_for_status()
    payload = response.json()
    metadata = gmail_metadata_from_payload(payload, message_id)
    body = decode_gmail_body(payload.get("payload", {}))
    gmail_cache_put(user["id"], message_id, metadata=metadata, body=body)
    return {**metadata, "date": gmail_message_date(metadata), "body": body}


def send_gmail_message(user, recipient, subject, body):
    access_token = get_gmail_access_token(user)
    if not access_token:
        raise RuntimeError("Google sign-in must be re-authorized before sending email.")
    email = EmailMessage()
    email["To"] = recipient
    email["Subject"] = subject or "(No subject)"
    email["From"] = user["email"]
    email.set_content(body)
    raw = base64.urlsafe_b64encode(email.as_bytes()).decode().rstrip("=")
    response = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"raw": raw},
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


def telegram_snapshot(config, user_id, limit=8):
    async def run():
        client = _telegram_client(config)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise RuntimeError(
                    "This Telegram session is no longer signed in. Connect your account again."
                )
            me = await client.get_me()
            dialogs = await client.get_dialogs(limit=limit)
            messages = []
            for dialog in dialogs:
                message = dialog.message
                if message is None:
                    continue
                messages.append(
                    {
                        "id": message.id,
                        "sender": getattr(dialog, "name", "") or "Telegram",
                        "text": message.message or "(No text content)",
                        "time": message.date.astimezone().strftime("%b %d, %H:%M"),
                    }
                )
            return _telegram_account(me), messages
        finally:
            await client.disconnect()

    with _telegram_lock(user_id):
        return asyncio.run(run())


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


SOCIAL_API_VERSION = "v22.0"
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
        "key": "facebook",
        "name": "Facebook",
        "mark": "f",
        "subtitle": "Pages, posts and feed",
        "help": "Open developers.facebook.com, create an app, and paste a Page access token with pages_manage_posts and pages_read_engagement.",
        "fields": [social_field("access_token", "Page access token", "password", "Paste your Page access token")],
        "test": True,
        "test_label": "Post to Page",
        "test_placeholder": "Hello from CentroMail",
        "max_length": 5000,
    },
    {
        "key": "instagram",
        "name": "Instagram",
        "mark": "Ig",
        "subtitle": "Business profile and feed",
        "help": "Use a Meta app with an Instagram Business account. Enter the Instagram user ID and an access token with instagram_basic.",
        "fields": [
            social_field("ig_user_id", "Instagram user ID", "text", "17841400000000000"),
            social_field("access_token", "Access token", "password", "Paste your access token"),
        ],
        "test": False,
        "note": "Instagram publishing requires an image or video URL, so CentroMail validates the connection here.",
    },
    {
        "key": "threads",
        "name": "Threads",
        "mark": "Th",
        "subtitle": "Text posts and profile",
        "help": "Create a Meta Threads app and paste a long-lived Threads access token with threads_basic and threads_content_publish.",
        "fields": [social_field("access_token", "Threads access token", "password", "Paste your Threads token")],
        "test": True,
        "test_label": "Post test thread",
        "test_placeholder": "Hello from CentroMail",
        "max_length": 500,
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


def social_profile(provider, config):
    token = config.get("access_token") or config.get("bot_token") or ""

    if provider == "x":
        data = social_request("https://api.x.com/2/users/me", token)
        user = data.get("data") or {}
        config["account"] = user.get("name") or "X account"
        config["detail"] = f"@{user['username']}" if user.get("username") else ""
    elif provider == "facebook":
        data = social_request(
            f"https://graph.facebook.com/{SOCIAL_API_VERSION}/me",
            params={"fields": "id,name", "access_token": token},
        )
        config["account"] = data.get("name") or "Facebook Page"
        config["detail"] = f"Page {data['id']}" if data.get("id") else ""
    elif provider == "instagram":
        data = social_request(
            f"https://graph.facebook.com/{SOCIAL_API_VERSION}/{config['ig_user_id']}",
            params={"fields": "id,username,account_type", "access_token": token},
        )
        config["account"] = "@" + data.get("username", "instagram")
        config["detail"] = data.get("account_type", "")
    elif provider == "threads":
        data = social_request(
            "https://graph.threads.net/v1.0/me",
            params={"fields": "id,username", "access_token": token},
        )
        config["account"] = "@" + data.get("username", "threads")
        config["detail"] = f"User {data['id']}" if data.get("id") else ""
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
        instance = (
            config.get("instance", "")
            .replace("https://", "")
            .replace("http://", "")
            .strip("/")
        )
        if not instance or "." not in instance:
            raise RuntimeError("Enter a Mastodon instance such as mastodon.social.")
        config["instance"] = instance
        base_url = "https://" + instance
        data = social_request(base_url + "/api/v1/accounts/verify_credentials", token)
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
            params={"fields": "open_id,display_name,username"},
        )
        user = (data.get("data") or {}).get("user") or {}
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
    elif provider == "facebook":
        social_request(
            f"https://graph.facebook.com/{SOCIAL_API_VERSION}/me/feed",
            method="POST",
            params={"access_token": token},
            payload={"message": text[:5000]},
        )
    elif provider == "threads":
        container = social_request(
            "https://graph.threads.net/v1.0/me/threads",
            method="POST",
            params={
                "media_type": "TEXT",
                "text": text[:500],
                "access_token": token,
            },
        )
        creation_id = container.get("id")
        if not creation_id:
            raise RuntimeError("Threads did not return a post container.")
        social_request(
            "https://graph.threads.net/v1.0/me/threads_publish",
            method="POST",
            params={"creation_id": creation_id, "access_token": token},
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
        social_request(
            config.get("base_url", "https://mastodon.social") + "/api/v1/statuses",
            token,
            method="POST",
            payload={"status": text[:500]},
        )
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
    return redirect(url_for('login'))

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
    remember = False
    if request.method == 'POST':
        email = normalize_email(request.form.get('email', ''))
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        if not valid_email(email):
            flash("Please enter a valid email address.", "error")
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
    return render_auth(email=email, remember=remember)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if g.user is not None:
        return redirect(url_for('dashboard'))
    email = session.get('pending_email', '')
    name = ''
    if request.method == 'POST':
        email = normalize_email(request.form.get('email', ''))
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirmation = request.form.get('confirm_password', '')
        if not name or len(name) > 100:
            flash("Enter a name between 1 and 100 characters.", "error")
        elif not valid_email(email):
            flash("Please enter a valid email address.", "error")
        elif not 12 <= len(password) <= 1024:
            flash("Use between 12 and 1024 characters for your password.", "error")
        elif password != confirmation:
            flash("Your passwords do not match.", "error")
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
    return render_auth(active_panel='signup', email=email, name=name)


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
        "gmail_cache", "gmail_sync_state", "gmail_folder_pages", "gmail_mailbox_counts",
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
    "important": {"title": "Important", "icon": "label_important", "label": "IMPORTANT"},
    "spam": {"title": "Spam", "icon": "report", "label": "SPAM"},
    "trash": {"title": "Trash", "icon": "delete", "label": "TRASH"},
}


def requested_mail_folder():
    folder = request.args.get("folder", "inbox")
    if folder not in GMAIL_FOLDERS:
        abort(404)
    return folder


def cached_mail_preview(user, folder):
    """Render a small local preview without contacting Gmail."""
    page = get_db().execute(
        "SELECT message_ids FROM gmail_folder_pages "
        "WHERE user_id = ? AND folder = ? AND query = '' AND cursor = ''",
        (user["id"], folder),
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
           AND (? = 'all' OR EXISTS (
               SELECT 1 FROM json_each(COALESCE(json_extract(metadata, '$.label_ids'), '["INBOX"]'))
               WHERE value = ?))
           ORDER BY CAST(json_extract(metadata, '$.internal_date') AS INTEGER) DESC LIMIT ?""",
        (user["id"], folder, label, MAIL_BATCH_SIZE),
    ).fetchall()
    return [json.loads(row["metadata"]) for row in rows]


def fetch_mail_page(user, folder, cursor="", query="", refresh=False):
    """Fetch one Gmail page, never walk the entire mailbox."""
    token = get_gmail_access_token(user)
    if not token:
        raise RuntimeError("Connect Google to load your email.")
    headers = {"Authorization": "Bearer " + token}
    db = get_db()
    cached = db.execute(
        "SELECT * FROM gmail_folder_pages WHERE user_id = ? AND folder = ? AND query = ? AND cursor = ?",
        (user["id"], folder, query, cursor),
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
        response = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers, params=params, timeout=(5, 15),
        )
        response.raise_for_status()
        payload = response.json()
        ids = [item["id"] for item in payload.get("messages", []) if item.get("id")][:MAIL_BATCH_SIZE]
        next_cursor = payload.get("nextPageToken")
        total = payload.get("resultSizeEstimate", len(ids))
        db.execute(
            """INSERT INTO gmail_folder_pages VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, folder, query, cursor) DO UPDATE SET
               message_ids = excluded.message_ids, next_cursor = excluded.next_cursor,
               total = excluded.total, listed_at = excluded.listed_at""",
            (user["id"], folder, query, cursor, json.dumps(ids), next_cursor, total, time.time()),
        )
        db.commit()
    messages, missing = {}, []
    for message_id in ids:
        metadata = None if refresh else gmail_cache_get(user["id"], message_id)
        if metadata is not None:
            messages[message_id] = metadata
        else:
            missing.append(message_id)
    # At most 25 metadata requests per page; other pages wait for scrolling.
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_gmail_detail, headers, item): item for item in missing}
        for future in as_completed(futures):
            message_id = futures[future]
            try:
                metadata = future.result()
            except requests.HTTPError as error:
                if gmail_error_status(error) in {404, 410}:
                    continue
                raise
            gmail_cache_put(user["id"], message_id, metadata=metadata)
            messages[message_id] = metadata
    return [messages[item] for item in ids if item in messages], next_cursor, total


@app.get('/api/mail/messages')
def mailbox_messages():
    folder = requested_mail_folder()
    query = request.args.get("search", "").strip()[:500]
    category = request.args.get("category", "")
    if folder == "inbox" and category in {"primary", "updates", "social"}:
        query = " ".join(filter(None, (query, "category:" + category)))
    try:
        messages, next_cursor, total = fetch_mail_page(
            g.user, folder, request.args.get("cursor", ""), query,
            refresh=request.args.get("refresh") == "1",
        )
    except RuntimeError as error:
        return jsonify(error=str(error), reconnect=True), 409
    except requests.HTTPError as error:
        return jsonify(error=gmail_error_message(error), reconnect=gmail_error_status(error) in {401, 403}), 502
    except (requests.RequestException, KeyError, ValueError):
        app.logger.exception("Could not load Gmail page")
        return jsonify(error="Could not load messages. Please try again."), 502
    return jsonify(
        html=render_template('mail_rows.html', messages=messages, folder=folder),
        next_cursor=next_cursor, total=total, count=len(messages),
    )


@app.get('/api/mail/counts')
def mailbox_counts():
    cached = get_db().execute(
        "SELECT counts, updated_at FROM gmail_mailbox_counts WHERE user_id = ?", (g.user["id"],)
    ).fetchone()
    if cached and time.time() - cached["updated_at"] < 60 and request.args.get("refresh") != "1":
        return jsonify(json.loads(cached["counts"]))
    try:
        token = get_gmail_access_token(g.user)
        if not token:
            return jsonify({})
        counts = {}
        for folder, label in (("inbox", "INBOX"), ("drafts", "DRAFT")):
            response = requests.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/labels/" + label,
                headers={"Authorization": "Bearer " + token}, timeout=(5, 10),
            )
            response.raise_for_status()
            info = response.json()
            counts[folder] = info.get("messagesUnread", 0) if folder == "inbox" else info.get("messagesTotal", 0)
        get_db().execute(
            "INSERT OR REPLACE INTO gmail_mailbox_counts VALUES (?, ?, ?)",
            (g.user["id"], json.dumps(counts), time.time()),
        )
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
    if action not in changes or not 1 <= len(ids) <= 50 or any(
        not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", item) for item in ids
    ):
        return jsonify(error="Select messages and choose a valid action."), 400
    add, remove = changes[action]
    try:
        token = get_gmail_access_token(g.user)
        if not token:
            return jsonify(error="Connect Google to change your email.", reconnect=True), 409
        response = requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/batchModify",
            headers={"Authorization": "Bearer " + token},
            json={"ids": ids, "addLabelIds": add, "removeLabelIds": remove}, timeout=(5, 20),
        )
        response.raise_for_status()
    except requests.HTTPError as error:
        if gmail_error_status(error) in {401, 403}:
            return jsonify(error="Reconnect Google to allow archiving, starring and changing messages.", reconnect=True), 403
        return jsonify(error=gmail_error_message(error)), 502
    except requests.RequestException:
        return jsonify(error="The message action failed. Please try again."), 502
    db = get_db()
    for message_id in ids:
        metadata = gmail_cache_get(g.user["id"], message_id)
        if metadata is not None:
            labels = (set(metadata.get("label_ids", ["INBOX"])) | set(add)) - set(remove)
            metadata.update(label_ids=sorted(labels), unread="UNREAD" in labels, starred="STARRED" in labels)
            gmail_cache_put(g.user["id"], message_id, metadata=metadata)
    for table in ("gmail_folder_pages", "gmail_mailbox_counts", "gmail_sync_state"):
        db.execute(f"DELETE FROM {table} WHERE user_id = ?", (g.user["id"],))
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
def inbox():
    folder = requested_mail_folder()
    messages = cached_mail_preview(g.user, folder)
    return render_template(
        'mail.html', messages=messages, folder=folder, folders=GMAIL_FOLDERS,
        folder_title=GMAIL_FOLDERS[folder]["title"], stats=make_stats(messages),
    )


@app.route('/mail')
def mail():
    return inbox()


@app.route('/message/<message_id>')
def message_detail(message_id):
    folder = requested_mail_folder()
    try:
        message = fetch_gmail_message(g.user, message_id)
        if message is None:
            raise RuntimeError("Connect Google to read this email.")
    except (RuntimeError, requests.RequestException, KeyError, ValueError) as error:
        if request.args.get("pane") == "1":
            return render_template('message_error.html', error="Could not open this email. Reconnect Google or try again."), 502
        return render_template(
            'message_unavailable.html', folder=folder, folder_title=GMAIL_FOLDERS[folder]["title"],
            error=str(error) if isinstance(error, RuntimeError) else "Could not open this email. Please try again.",
        )
    return render_template(
        'message_pane.html' if request.args.get("pane") == "1" else 'message.html',
        message=message, folder=folder, folder_title=GMAIL_FOLDERS[folder]["title"],
    )


@app.post('/compose')
def compose():
    """Send a message from the in-page composer. There is no compose page."""
    recipient = normalize_email(request.form.get('to', ''))
    subject = request.form.get('subject') or 'No subject'
    body = request.form.get('body') or ''
    if not valid_email(recipient):
        flash("Enter a valid recipient email address.", "error")
    elif not body.strip():
        flash("Write a message before sending.", "error")
    else:
        try:
            send_gmail_message(g.user, recipient, subject, body)
        except RuntimeError as error:
            flash(str(error), "error")
        except requests.RequestException:
            flash("Gmail could not send the message. Please try again.", "error")
        else:
            flash(f"Message sent to {recipient} successfully.", "success")
    return redirect(url_for('inbox'))


@app.route('/settings')
def settings():
    return render_template('settings.html')


@app.get('/integrations')
def integrations():
    telegram = get_integration(g.user["id"], "telegram")
    telegram_stage = telegram.get("stage") if telegram else None
    telegram_account = telegram.get("account") if telegram else None
    updates = []
    telegram_error = None
    if telegram_stage == "connected":
        try:
            telegram_account, updates = telegram_snapshot(telegram, g.user["id"])
        except Exception as error:
            telegram_error = telegram_error_text(error)
            app.logger.warning(
                "Telegram sync failed for user id=%s: %s", g.user["id"], telegram_error
            )
    whatsapp = get_integration(g.user["id"], "whatsapp")
    discord = get_integration(g.user["id"], "discord")
    discord_messages = []
    discord_error = None
    if discord is not None:
        try:
            discord_messages = discord_recent_messages(discord)
        except Exception as error:
            discord_error = str(error)
            app.logger.warning(
                "Discord sync failed for user id=%s: %s", g.user["id"], discord_error
            )
    social_cards = [
        {
            "spec": spec,
            "config": get_integration(g.user["id"], "social:" + spec["key"]),
        }
        for spec in SOCIAL_PROVIDERS
    ]
    social_state = [
        {
            "key": card["spec"]["key"],
            "name": card["spec"]["name"],
            "connected": bool(card["config"]),
            "account": (card["config"] or {}).get("account", ""),
        }
        for card in social_cards
    ]
    return render_template(
        'integrations.html',
        telegram=telegram,
        telegram_stage=telegram_stage,
        telegram_account=telegram_account,
        telegram_updates=updates,
        telegram_error=telegram_error,
        telegram_available=telegram_available(),
        whatsapp=whatsapp,
        whatsapp_messages=whatsapp_recent_messages(g.user["id"]) if whatsapp else [],
        whatsapp_webhook_url=url_for('whatsapp_webhook', _external=True),
        discord=discord,
        discord_messages=discord_messages,
        discord_error=discord_error,
        social_cards=social_cards,
        social_state=social_state,
        google_connected=bool(get_google_token(g.user)),
        google_email=session.get("user_email"),
    )


@app.post('/integrations/telegram/start')
def telegram_start_route():
    api_id_text = request.form.get("api_id", "").strip()
    api_hash = request.form.get("api_hash", "").strip()
    phone = re.sub(r"[\s().-]", "", request.form.get("phone", ""))
    if not api_id_text.isdigit() or not 1 <= int(api_id_text) <= 2147483647:
        flash("Enter the numeric API ID from my.telegram.org.", "error")
        return redirect(url_for('integrations'))
    if not TELEGRAM_API_HASH_RE.fullmatch(api_hash):
        flash("Enter the 32-character API hash from my.telegram.org.", "error")
        return redirect(url_for('integrations'))
    if not TELEGRAM_PHONE_RE.fullmatch(phone):
        flash("Enter your phone number in international format, for example +233201234567.", "error")
        return redirect(url_for('integrations'))
    if not telegram_available():
        flash("Telegram account support is not installed. Run pip install telethon.", "error")
        return redirect(url_for('integrations'))
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
    return redirect(url_for('integrations'))


@app.post('/integrations/telegram/verify')
def telegram_verify_route():
    code = re.sub(r"\s+", "", request.form.get("code", ""))
    if not code:
        flash("Enter the login code Telegram sent you.", "error")
        return redirect(url_for('integrations'))
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
    return redirect(url_for('integrations'))


@app.post('/integrations/telegram/password')
def telegram_password_route():
    password = request.form.get("password", "")
    if not password:
        flash("Enter your Telegram two-step verification password.", "error")
        return redirect(url_for('integrations'))
    try:
        telegram_verify(g.user, password, "password")
    except Exception as error:
        message = telegram_error_text(error)
        app.logger.warning("Telegram password sign-in failed for user id=%s: %s", g.user["id"], message)
        flash(f"Telegram sign-in failed: {message}", "error")
    else:
        flash("Telegram account connected and saved on this device.", "success")
    return redirect(url_for('integrations'))


@app.post('/integrations/telegram/restart')
def telegram_restart_route():
    delete_integration(g.user["id"], "telegram")
    flash("Telegram sign-in restarted.", "info")
    return redirect(url_for('integrations'))


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
        return redirect(url_for('integrations'))
    if not access_token or len(access_token) > 4096:
        flash("Enter a valid WhatsApp Cloud API access token.", "error")
        return redirect(url_for('integrations'))
    if verify_token and not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", verify_token):
        flash("The webhook verify token must be 8-64 letters, numbers, underscores or dashes.", "error")
        return redirect(url_for('integrations'))
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
    return redirect(url_for('integrations'))


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

    payload = request.get_json(silent=True) or {}
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
        return redirect(url_for('integrations'))
    if not 15 <= len(channel_id) <= 25:
        flash("Enter the numeric Discord channel ID.", "error")
        return redirect(url_for('integrations'))
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
    return redirect(url_for('integrations'))


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
    return redirect(url_for('integrations'))


@app.post('/integrations/social/<provider>/test')
def test_social_route(provider):
    spec = SOCIAL_PROVIDERS_BY_KEY.get(provider)
    if spec is None:
        abort(404)
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
        if not app.config["GOOGLE_CLIENT_ID"] or not app.config["GOOGLE_CLIENT_SECRET"]:
            flash("Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", "error")
            return redirect(url_for('login'))
        return google.authorize_redirect(google_callback_uri())

    flash(f'{provider.title()} sign-in is not available yet. Please continue with email.', 'info')
    return redirect(url_for('login'))


@app.get('/auth/google/callback')
def google_callback():
    if not app.config["GOOGLE_CLIENT_ID"] or not app.config["GOOGLE_CLIENT_SECRET"]:
        flash("Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", "error")
        return redirect(url_for('login'))

    if request.args.get("error"):
        flash("Google sign-in was cancelled or denied. Please try again.", "error")
        return redirect(url_for('login'))

    try:
        token = google.authorize_access_token()
    except OAuthError as error:
        if error.error == "invalid_grant":
            message = "Google rejected the authorization code. Start sign-in again and use the same browser address."
        else:
            message = "Google sign-in could not be completed. Check the OAuth callback URI and try again."
        flash(message, "error")
        return redirect(url_for('login'))

    profile = token.get("userinfo")
    if not profile or profile.get("email_verified") is not True:
        flash("Google did not provide a verified email address.", "error")
        return redirect(url_for('onboarding'))

    email = normalize_email(profile.get("email", ""))
    if not valid_email(email):
        flash("Google did not provide a valid email address.", "error")
        return redirect(url_for('onboarding'))

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


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
