"""The Flask app instance, and what every request gets: HTTPS, cross-site request checks, headers.

Kept in its own module so blueprints can import it without going through the
package __init__ (which would be circular).
"""
import os
from urllib.parse import urlsplit

from flask import Flask, jsonify, redirect, request

from .paths import STATIC_DIR, TEMPLATES_DIR

app = Flask(
    "Lectern",
    static_folder=STATIC_DIR,
    template_folder=TEMPLATES_DIR,
)

# Behind a proxy (nginx) that terminates HTTPS: trust its X-Forwarded-For and -Proto (one hop), so the
# client's address is right for rate limits and https is seen as https. (Not -Host: the address in
# links Lectern emails comes only from LECTERN_APP_URL.) Lectern must then listen only on 127.0.0.1,
# so nothing can reach it except through the proxy (see the README).
if os.environ.get("LECTERN_BEHIND_PROXY"):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Uploads (a course page's files) arrive in one save; nothing needs more than this. Everything else
# is small JSON, and gets a much smaller limit (see _guard).
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get("LECTERN_MAX_UPLOAD_MB") or 64) * 1024 * 1024
SMALL_BODY = 256 * 1024

# ── No caching ─────────────────────────────────────────────────────────────
# Lectern is edited constantly, and a browser holding on to an old copy of a
# tool costs far more than re-fetching it. Flask's default for static files is
# a 12-hour max-age, which is how a stale build survives an edit and a reload.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def is_local():
    """Running on this computer (http://localhost counts as a secure page, so plain HTTP is fine there)."""
    return (request.host.rsplit(":", 1)[0] if not request.host.startswith("[") else request.host.split("]")[0] + "]") in LOCAL_HOSTS


def secure_enough():
    return request.is_secure or is_local()


def _host_of(url):
    return (urlsplit(url).hostname or "").lower()


def configured_url():
    url = os.environ.get("LECTERN_APP_URL", "")
    return (url if url.endswith("/") else url + "/") if url else ""


def app_url():
    """Lectern's address: LECTERN_APP_URL, or (only when it's unset) the address this request came to.
    Links in emails use link_base() instead, which never trusts the request."""
    return configured_url() or request.host_url


def link_base():
    """The address for links in emails (invitations, resets): LECTERN_APP_URL, or localhost while
    developing. Never the request's Host header, which anyone can set (to point a reset link at their site)."""
    if configured_url():
        return configured_url()
    if is_local():
        return request.host_url
    return None


def trusted_hosts():
    hosts = [h for h in (_host_of(configured_url()), _host_of(os.environ.get("LECTERN_PAGES_URL", "")), _host_of(os.environ.get("LECTERN_ADMIN_URL", ""))) if h]
    return hosts + ["localhost", "127.0.0.1", "::1"] if hosts else []


# With LECTERN_APP_URL set, requests for any other host are refused (Flask's TRUSTED_HOSTS).
if trusted_hosts():
    app.config["TRUSTED_HOSTS"] = trusted_hosts()


def _origin(url):
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}".lower()


# Student-facing endpoints: no account, no cookie used, open to any page (see accommodations.py).
PUBLIC_POSTS = {"/api/accommodations/verify", "/api/accommodations/submit"}


@app.before_request
def _guard():
    # Only saves (a course page's uploads) may be big; sign-in and the rest are small JSON.
    if not (request.path.startswith("/api/store/") and request.path.endswith("/git/blobs")):
        request.max_content_length = SMALL_BODY
    # Anything but localhost goes over HTTPS: passwords and session cookies never travel in the clear.
    if not secure_enough():
        if request.method in ("GET", "HEAD"):
            return redirect(request.url.replace("http://", "https://", 1), code=301)
        return jsonify(error="Lectern only works over HTTPS."), 403
    # Changes made with a session cookie must come from Lectern's own pages: a custom header (which a
    # page on another site can't send without CORS, which we never allow) and, when the browser says
    # where the request came from, that it's here. SameSite cookies are a second layer.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.path.startswith("/api/") and request.path not in PUBLIC_POSTS:
        if request.headers.get("X-Lectern") != "1":
            return jsonify(error="Refused: this request didn't come from Lectern."), 403
        org = request.headers.get("Origin")
        if org and _origin(org) not in {_origin(request.host_url), _origin(app_url())}:
            return jsonify(error="Refused: this request came from another site."), 403
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return jsonify(error="Refused: this request came from another site."), 403


@app.after_request
def _headers(resp):
    h = resp.headers
    if (request.path or '').startswith('/api/'):
        # Sign-in responses carry secrets: never cache them anywhere.
        h['Cache-Control'] = 'no-store'
    elif not (request.path or '').startswith('/p/'):
        h['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        h['Pragma'] = 'no-cache'
        h['Expires'] = '0'
    h.setdefault('X-Content-Type-Options', 'nosniff')
    h.setdefault('Referrer-Policy', 'same-origin')
    h.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
    h.setdefault('Permissions-Policy', 'camera=(self), microphone=(), geolocation=(), payment=()')
    if request.is_secure:
        h.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    if (request.path or '').startswith('/c/'):
        # A course page: it can be embedded in the university's Quercus (Canvas) pages, and nowhere else.
        h.setdefault('Content-Security-Policy', csp(frame_ancestors=EMBED_FROM))
    elif not (request.path or '').startswith('/p/'):
        # Lectern's own pages: never inside another site's frame (clickjacking), no plugins, no <base> tricks.
        h.setdefault('X-Frame-Options', 'DENY')
        h.setdefault('Content-Security-Policy', csp())
    return resp


# Lectern's own pages: scripts only from here (and the one library the Exam Builder loads, KaTeX, from
# its exact folder on the CDN), so an injected <script> or onclick= won't run; nothing framed; calls only
# to here (and GitHub, for a builder opened on its own at /tools/<name>.html, which tools.py allows its
# own inline script by hash).
KATEX = "https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.9/"


# Where a course page (/c/...) may be embedded: Lectern itself, and Quercus (U of T's Canvas, and Canvas's own
# addresses, which Quercus's pages can be served from). LECTERN_EMBED_FROM, if set, replaces the list.
EMBED_FROM = os.environ.get("LECTERN_EMBED_FROM", "https://q.utoronto.ca https://*.instructure.com")


def csp(extra_scripts="", frame_ancestors=""):
    return "; ".join([
        "default-src 'self'",
        # Only Lectern's own code: /static/ and /tools/ (not /p/, where people's published files are).
        # 'wasm-unsafe-eval': WebAssembly from /static/vendor/ (Attendance's card reader); it can't run a string as code.
        f"script-src {request.host_url}static/ {request.host_url}tools/ {KATEX} 'wasm-unsafe-eval'{(' ' + extra_scripts) if extra_scripts else ''}",
        f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {KATEX}",
        f"font-src 'self' data: https://fonts.gstatic.com {KATEX}",
        "img-src 'self' data: blob: https:",
        "connect-src 'self' https://api.github.com",
        "frame-src 'none'", f"frame-ancestors 'self' {frame_ancestors}" if frame_ancestors else "frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'", "form-action 'self'",
    ])


@app.errorhandler(413)
def _too_big(e):
    return jsonify(error=f"That's too big to save (over {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB at once)."), 413
