import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.flask_client import OAuth
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
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
    client_kwargs={"scope": "openid email profile"},
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        columns = {column[1] for column in db.execute("PRAGMA table_info(users)")}
        if "name" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''")
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


messages = []


def make_stats():
    return {
        'total': len(messages),
        'unread': sum(1 for message in messages if message['unread']),
        'starred': sum(1 for message in messages if message['starred']),
        'sent': 12,
    }


@app.route('/')
def index():
    return redirect(url_for('login'))

@app.get('/onboarding')
def onboarding():
    if g.user is not None:
        return redirect(url_for('dashboard'))
    return render_template('onboard.html')


@app.post('/continue')
def continue_flow():
    if g.user is not None:
        return redirect(url_for('dashboard'))
    email = normalize_email(request.form.get('email', ''))
    if not valid_email(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for('onboarding'))
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
    return render_template('dashboard.html', stats=make_stats(), user_email=session.get('user_email'))


@app.route('/inbox')
def inbox():
    return render_template('mail.html', messages=messages, stats=make_stats())


@app.route('/mail')
def mail():
    return render_template('mail.html', messages=messages, stats=make_stats())


@app.route('/message/<int:message_id>')
def message_detail(message_id):
    for message in messages:
        if message['id'] == message_id:
            return render_template('message.html', message=message)
    return render_template('mail.html', messages=messages, stats=make_stats())


@app.route('/compose', methods=['GET', 'POST'])
def compose():
    if request.method == 'POST':
        recipient = request.form.get('to', 'unknown@example.com')
        subject = request.form.get('subject') or 'No subject'
        body = request.form.get('body') or ''
        flash(f'Message sent to {recipient} successfully.', 'success')
        print(f'Sent email to {recipient} | Subject: {subject} | Body: {body}')
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
            return redirect(url_for('onboarding'))
        callback_uri = (
            app.config["GOOGLE_REDIRECT_URI"]
            or url_for("google_callback", _external=True)
        )
        return google.authorize_redirect(callback_uri)

    flash(f'{provider.title()} sign-in is not available yet. Please continue with email.', 'info')
    return redirect(url_for('onboarding'))


@app.get('/auth/google/callback')
def google_callback():
    if not app.config["GOOGLE_CLIENT_ID"] or not app.config["GOOGLE_CLIENT_SECRET"]:
        flash("Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", "error")
        return redirect(url_for('onboarding'))

    try:
        token = google.authorize_access_token()
    except OAuthError:
        flash("Google sign-in was not completed. Please try again.", "error")
        return redirect(url_for('onboarding'))

    profile = token.get("userinfo")
    if not profile or profile.get("email_verified") is not True:
        flash("Google did not provide a verified email address.", "error")
        return redirect(url_for('onboarding'))

    email = normalize_email(profile.get("email", ""))
    if not valid_email(email):
        flash("Google did not provide a valid email address.", "error")
        return redirect(url_for('onboarding'))

    user = find_user(email)
    if user is None:
        name = (profile.get("name") or email.split("@", 1)[0]).strip()[:100]
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name or email, email, generate_password_hash(secrets.token_urlsafe(32))),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
        user = find_user(email)
    if user is None:
        abort(500, description="Could not create or find the Google account.")

    sign_in(user)
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
