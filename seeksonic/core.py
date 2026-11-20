"""
SeekSonic
=============================

A Subsonic-compatible proxy that sits in front of Navidrome and injects
lyric-based matches (from a Meilisearch index) into search2/search3 results.
Everything else is passed straight through to Navidrome.

Environment variables
---------------------
NAVIDROME_URL            Base URL of Navidrome            (default http://navidrome:4533)
NAVIDROME_USER           Navidrome user used for indexing (required)
NAVIDROME_PASSWORD       Password for that user (required)
MEILISEARCH_URL          Base URL of Meilisearch          (default http://navidrome-search-meili:7700)
MEILI_MASTER_KEY         Meilisearch API key
SYNC_INTERVAL_MINUTES    Background sync interval, 0 disables (default 30)
SYNC_WORKERS             Parallel Navidrome requests during sync (default 4)
LYRIC_MATCH_LIMIT        Maximum lyric matches injected per search (default 5, max 50)
ADMIN_USER               Username for the management UI / admin API (required)
ADMIN_PASSWORD           Management UI password (required; minimum 8 characters)
ADMIN_SESSION_SECRET     Flask session signing secret (required; minimum 32 characters)
MEILI_TASK_TIMEOUT       Maximum wait for Meilisearch mutation tasks (default 120)
WAITRESS_THREADS         Waitress worker threads (default 8)
DB_PATH                  SQLite state file                (default /app/data/sync_state.db)
HOST / PORT              Bind address                     (default 0.0.0.0 / 8080)
LOG_LEVEL                Python log level                 (default INFO)
"""
import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps
from http.cookiejar import CookiePolicy
from xml.sax.saxutils import quoteattr
from urllib.parse import urlsplit

import requests
from flask import Flask, Response, g, jsonify, redirect, render_template_string, request, session
from requests.adapters import HTTPAdapter

# ---------------------------------------------------------------------------
# Logging (with credential redaction: Subsonic auth travels in the query string)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("lyrics-proxy")

_SECRET_PARAM_RE = re.compile(r"([?&](?:t|s|p|apiKey)=)[^&\s\"']+")


def redact(text):
    """Mask Subsonic credential parameters (t, s, p, apiKey) in any text."""
    return _SECRET_PARAM_RE.sub(r"\1***", str(text))


class _RedactFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


logging.getLogger("werkzeug").addFilter(_RedactFilter())

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _env_int(name, default, minimum=None):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        log.warning("Invalid value for %s, using default %s", name, default)
        value = default
    return max(minimum, value) if minimum is not None else value


NAVIDROME_URL = os.environ.get("NAVIDROME_URL", "http://navidrome:4533").rstrip("/")
NAVIDROME_USER = os.environ.get("NAVIDROME_USER", "lyrics")
NAVIDROME_PASSWORD = os.environ.get("NAVIDROME_PASSWORD", "")
MEILISEARCH_URL = os.environ.get("MEILISEARCH_URL", "http://navidrome-search-meili:7700").rstrip("/")
MEILI_MASTER_KEY = os.environ.get("MEILI_MASTER_KEY", "")
SYNC_INTERVAL_MINUTES = _env_int("SYNC_INTERVAL_MINUTES", 30, minimum=0)
SYNC_WORKERS = min(_env_int("SYNC_WORKERS", 4, minimum=1), 16)
WAITRESS_THREADS = min(_env_int("WAITRESS_THREADS", 8, minimum=1), 32)
MEILI_TASK_TIMEOUT = min(_env_int("MEILI_TASK_TIMEOUT", 120, minimum=10), 600)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_SESSION_SECRET = os.environ.get("ADMIN_SESSION_SECRET", "")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = _env_int("PORT", 8080, minimum=1)

INDEX_NAME = "navidrome_lyrics"
DB_PATH = os.environ.get("DB_PATH", "/app/data/sync_state.db")
CHUNK_SIZE = 100          # tracks fetched + sent to Meilisearch per batch
LYRIC_MATCH_LIMIT = min(_env_int("LYRIC_MATCH_LIMIT", 5, minimum=1), 50)  # lyric hits injected into search results
SUBSONIC_NS = "http://subsonic.org/restapi"

app = Flask(__name__, static_folder="../static")
app.secret_key = ADMIN_SESSION_SECRET or None
app.config.update(
    MAX_CONTENT_LENGTH=32 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() in ("1", "true", "yes"),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)
ET.register_namespace("", SUBSONIC_NS)  # emit <subsonic-response xmlns=...> not ns0:

indexing_status = {
    "is_running": False,
    "total_tracks": 0,
    "processed_tracks": 0,
    "indexed_count": 0,
    "skipped_count": 0,
    "missing_lyrics_count": 0,
    "error_count": 0,
    "deleted_count": 0,
    "current_action": "Idle",
    "last_error": None,
    "last_sync_time": None,
}

# ---------------------------------------------------------------------------
# Per-thread HTTP sessions. Cookies and ambient proxy/.netrc settings are disabled.
# ---------------------------------------------------------------------------
class _NoCookies(CookiePolicy):
    return_ok = set_ok = domain_return_ok = path_return_ok = lambda self, *a, **k: False
    netscape = True
    rfc2965 = hide_cookie2 = False


_http_local = threading.local()


def http_session():
    """Return a thread-local pooled session; Requests Session is not shared across threads."""
    session = getattr(_http_local, "session", None)
    if session is None:
        session = requests.Session()
        session.trust_env = False  # Ignore ambient proxy and .netrc credentials.
        session.cookies.set_policy(_NoCookies())
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _http_local.session = session
    return session


_lookup_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="lookup")

# ---------------------------------------------------------------------------
# Admin authentication (signed, time-limited browser sessions)
# ---------------------------------------------------------------------------
def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not ADMIN_PASSWORD or not ADMIN_SESSION_SECRET:
            return Response("Administrator authentication is not configured", 503)
        if session.get("admin_user") != ADMIN_USER:
            if request.path == "/":
                return redirect("/login")
            return jsonify({"error": "Authentication required"}), 401
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            expected = session.get("csrf_token", "")
            supplied = request.headers.get("X-CSRF-Token", "")
            if not expected or not hmac.compare_digest(expected, supplied):
                return jsonify({"error": "CSRF validation failed"}), 403
        return view(*args, **kwargs)
    return wrapper


LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">

<!-- Application favicon -->
<link rel="icon" href="/static/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32.png">

<!-- Mobile / Apple -->
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png">

<title>Sign in · SeekSonic</title>

<style>
:root {
    color-scheme: dark;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 20px;
    background: radial-gradient(ellipse at top, #14243a 0%, #0b1120 58%);
    color: #e6edf7;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}

.login {
    width: min(100%, 390px);
    background: #111c2e;
    border: 1px solid #26364d;
    border-radius: 16px;
    padding: 28px;
    box-shadow: 0 20px 60px #0005;
}

/* Center logo, heading and description only */
.login .logo,
.login h1,
.login > p {
    text-align: center;
}

.login .logo {
    display: flex;
    justify-content: center;
    margin-bottom: 16px;
}

.login .logo img {
    display: block;
    object-fit: contain;
}

h1 {
    font-size: 1.45rem;
    margin: 0 0 6px;
}

p {
    color: #91a2b9;
    font-size: .9rem;
    margin: 0 0 22px;
}

label {
    display: block;
    font-size: .82rem;
    margin: 14px 0 6px;
    color: #c3d0e0;
}

input {
    width: 100%;
    padding: 12px;
    border: 1px solid #3b506b;
    border-radius: 8px;
    background: #091525;
    color: #fff;
    font-size: 1rem;
}

button {
    width: 100%;
    margin-top: 20px;
    padding: 12px;
    border: 1px solid #0ea5e9;
    border-radius: 8px;
    background: #0284c7;
    color: white;
    font-weight: 700;
    font-size: .95rem;
    cursor: pointer;
}

button:disabled {
    opacity: .6;
    cursor: wait;
}

#error {
    min-height: 1.2em;
    color: #fca5a5;
    font-size: .84rem;
    margin: 12px 0 0;
}
</style>
</head>

<body>

<main class="login">

    <!-- SeekSonic logo -->
    <div class="logo">
        <img src="/static/logo.png"
             alt="SeekSonic"
             width="100"
             height="100">
    </div>

    <h1>SeekSonic</h1>

    <p>Sign in to the administration dashboard.</p>

    <form id="login-form">

        <label for="username">Username</label>
        <input id="username"
               name="username"
               autocomplete="username"
               required
               autofocus>

        <label for="password">Password</label>
        <input id="password"
               name="password"
               type="password"
               autocomplete="current-password"
               required>

        <button id="submit" type="submit">Sign in</button>

        <div id="error" role="alert"></div>

    </form>

</main>

<script nonce="{{ nonce }}">
const form = document.getElementById('login-form');

form.addEventListener('submit', async event => {
    event.preventDefault();

    const button = document.getElementById('submit');
    const error = document.getElementById('error');

    button.disabled = true;
    error.textContent = '';

    try {
        const response = await fetch('/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': '{{ csrf_token }}'
            },
            body: JSON.stringify({
                username: document.getElementById('username').value,
                password: document.getElementById('password').value,
                csrf_token: '{{ csrf_token }}'
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Sign-in failed');
        }

        window.location.assign('/');

    } catch (err) {
        error.textContent = err.message || 'Sign-in failed';

    } finally {
        button.disabled = false;
    }
});
</script>

</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if not ADMIN_PASSWORD or not ADMIN_SESSION_SECRET:
        return Response("Administrator authentication is not configured", 503)
    if request.method == "GET":
        if session.get("admin_user") == ADMIN_USER:
            return redirect("/")
        token = session.get("csrf_token") or secrets.token_urlsafe(32)
        session["csrf_token"] = token
        g.csp_nonce = secrets.token_urlsafe(16)
        return render_template_string(LOGIN_TEMPLATE, nonce=g.csp_nonce, csrf_token=token)

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid login request"}), 400
    expected = session.get("csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    body_token = payload.get("csrf_token", "")
    if (not expected or not hmac.compare_digest(expected, supplied)
            or not hmac.compare_digest(expected, str(body_token))):
        return jsonify({"error": "CSRF validation failed"}), 403

    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    valid = (hmac.compare_digest(username.encode(), ADMIN_USER.encode())
             and hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()))
    if not valid:
        return jsonify({"error": "Invalid username or password"}), 401

    session.clear()
    session.permanent = True
    session["admin_user"] = ADMIN_USER
    session["csrf_token"] = secrets.token_urlsafe(32)
    return jsonify({"status": "ok"})


@app.route("/logout", methods=["POST"])
@admin_required
def logout():
    session.clear()
    return jsonify({"status": "logged_out"})



@app.after_request
def add_security_headers(resp):
    """Hardening headers for the UI/API only; proxied /rest/ traffic is untouched."""
    if request.path.startswith("/rest/"):
        return resp

    nonce = g.get("csp_nonce")
    script_src = f"'nonce-{nonce}'" if nonce else "'none'"

    resp.headers["Content-Security-Policy"] = (
        f"default-src 'none'; "
        f"script-src {script_src}; "
        "style-src 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'none'"
    )

    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"

    return resp

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
@contextmanager
def get_db():
    """SQLite connection that commits/rolls back AND closes (the stdlib context
    manager alone leaves the connection open)."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS track_state (
                song_id TEXT PRIMARY KEY,
                title TEXT,
                artist TEXT,
                album TEXT,
                lyrics_hash TEXT,
                indexed_at INTEGER,
                status TEXT,
                last_error TEXT
            )
        """)


UPSERT_SQL = (
    "INSERT OR REPLACE INTO track_state "
    "(song_id, title, artist, album, lyrics_hash, indexed_at, status, last_error) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


def get_database_stats():
    """Return persistent track-state counts, independent of the current sync run."""
    counts = {"indexed": 0, "no_lyrics": 0, "error": 0, "deleted": 0, "total": 0}
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM track_state GROUP BY status"
            ).fetchall()
        for row in rows:
            key = row["status"]
            if key in counts:
                counts[key] = row["count"]
        counts["total"] = sum(counts[k] for k in ("indexed", "no_lyrics", "error", "deleted"))
    except sqlite3.Error as exc:
        log.warning("Could not read persistent database statistics: %s", type(exc).__name__)
        counts["unavailable"] = True
    return counts


# ---------------------------------------------------------------------------
# Meilisearch
# ---------------------------------------------------------------------------



__all__ = ['hashlib', 'hmac', 'logging', 'os', 're', 'secrets', 'sqlite3', 'threading', 'time', 'ET', 'ThreadPoolExecutor', 'contextmanager', 'timedelta', 'wraps', 'CookiePolicy', 'quoteattr', 'urlsplit', 'requests', 'Flask', 'Response', 'g', 'jsonify', 'redirect', 'render_template_string', 'request', 'session', 'HTTPAdapter', 'log', '_SECRET_PARAM_RE', 'redact', '_RedactFilter', '_env_int', 'NAVIDROME_URL', 'NAVIDROME_USER', 'NAVIDROME_PASSWORD', 'MEILISEARCH_URL', 'MEILI_MASTER_KEY', 'SYNC_INTERVAL_MINUTES', 'SYNC_WORKERS', 'WAITRESS_THREADS', 'MEILI_TASK_TIMEOUT', 'ADMIN_USER', 'ADMIN_PASSWORD', 'ADMIN_SESSION_SECRET', 'HOST', 'PORT', 'INDEX_NAME', 'DB_PATH', 'CHUNK_SIZE', 'LYRIC_MATCH_LIMIT', 'SUBSONIC_NS', 'app', 'indexing_status', '_NoCookies', '_http_local', 'http_session', '_lookup_pool', 'admin_required', 'LOGIN_TEMPLATE', 'login', 'logout', 'add_security_headers', 'get_db', 'init_db', 'UPSERT_SQL', 'get_database_stats']
