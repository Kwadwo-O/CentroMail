import os
import json
import base64
import logging
import re
import secrets
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

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
    client_kwargs={"scope": "openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"},
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
    if request.method == "POST":
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


def gmail_header(headers, name):
    return next(
        (header["value"] for header in headers if header.get("name", "").lower() == name.lower()),
        "",
    )


def gmail_sender(value):
    if "<" in value and value.endswith(">"):
        return value.rsplit("<", 1)[0].strip().strip('"') or value
    return value or "Unknown sender"


def gmail_message_time(value):
    try:
        return parsedate_to_datetime(value).astimezone().strftime("%b %d").replace(" 0", " ")
    except (TypeError, ValueError, OverflowError):
        return ""


def fetch_gmail_messages(user):
    app.logger.info("Starting Gmail inbox pull for user id=%s", user["id"])
    access_token = get_gmail_access_token(user)
    if not access_token:
        app.logger.warning("Gmail inbox pull skipped: no usable token for user id=%s", user["id"])
        return []
    headers = {"Authorization": "Bearer " + access_token}
    message_ids = []
    next_page_token = None
    page_count = 0
    while True:
        params = {
            "userId": "me",
            "labelIds": "INBOX",
            "maxResults": 50,
        }
        if next_page_token:
            params["pageToken"] = next_page_token
        response = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        page = response.json()
        page_count += 1
        message_ids.extend(item["id"] for item in page.get("messages", []) if item.get("id"))
        next_page_token = page.get("nextPageToken")
        if not next_page_token:
            break

    def fetch_message_detail(message_id):
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
        payload = detail.json()
        message_headers = payload.get("payload", {}).get("headers", [])
        label_ids = set(payload.get("labelIds", []))
        return {
            "id": payload.get("id", message_id),
            "sender": gmail_sender(gmail_header(message_headers, "From")),
            "subject": gmail_header(message_headers, "Subject") or "(No subject)",
            "preview": payload.get("snippet", ""),
            "time": gmail_message_time(gmail_header(message_headers, "Date")),
            "unread": "UNREAD" in label_ids,
            "starred": "STARRED" in label_ids,
            "category": "social" if "CATEGORY_SOCIAL" in label_ids else (
                "updates" if "CATEGORY_UPDATES" in label_ids else "primary"
            ),
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        messages = list(executor.map(fetch_message_detail, message_ids))
    app.logger.info(
        "Completed Gmail inbox pull for user id=%s: pages=%s messages=%s",
        user["id"],
        page_count,
        len(messages),
    )
    return messages


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
    return render_template('dashboard.html', stats=make_stats([]), user_email=session.get('user_email'))


@app.route('/inbox')
def inbox():
    try:
        messages = fetch_gmail_messages(g.user)
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else "unknown"
        app.logger.error("Gmail inbox pull failed with HTTP error: status=%s", status)
        if error.response is not None and error.response.status_code == 403:
            flash("Gmail access is unavailable because the Gmail API is disabled for this Google project. Enable the Gmail API in Google Cloud Console, then sign in with Google again.", "error")
        else:
            flash("Gmail could not be loaded right now. Please try again.", "error")
        messages = []
    except requests.Timeout:
        app.logger.error("Gmail inbox pull timed out")
        flash("Gmail took too long to respond. Please try again.", "error")
        messages = []
    except (requests.RequestException, KeyError, ValueError):
        app.logger.exception("Gmail inbox pull failed")
        flash("Gmail could not be loaded right now. Please try again.", "error")
        messages = []
    if not get_google_token(g.user):
        flash("Connect Google again to load your Gmail inbox.", "info")
    return render_template('mail.html', messages=messages, stats=make_stats(messages))


@app.route('/mail')
def mail():
    return inbox()


@app.route('/message/<message_id>')
def message_detail(message_id):
    try:
        messages = fetch_gmail_messages(g.user)
    except requests.HTTPError as error:
        app.logger.error("Gmail message pull failed with HTTP error: status=%s", error.response.status_code if error.response else "unknown")
        if error.response is not None and error.response.status_code == 403:
            flash("Gmail access is unavailable because the Gmail API is disabled for this Google project. Enable the Gmail API in Google Cloud Console, then sign in with Google again.", "error")
        else:
            flash("Gmail could not be loaded right now. Please try again.", "error")
        messages = []
    except (requests.RequestException, KeyError, ValueError):
        app.logger.exception("Gmail message pull failed")
        flash("Gmail could not be loaded right now. Please try again.", "error")
        messages = []
    for message in messages:
        if message['id'] == message_id:
            return render_template('message.html', message=message)
    return render_template('mail.html', messages=messages, stats=make_stats(messages))


@app.route('/compose', methods=['GET', 'POST'])
def compose():
    if request.method == 'POST':
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
    return render_template('compose.html')


@app.route('/settings')
def settings():
    return render_template('settings.html')


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
