"""The Flask app instance.

Kept in its own module so blueprints can import it without going through the
package __init__ (which would be circular).
"""
from flask import Flask, request

from .paths import STATIC_DIR, TEMPLATES_DIR

app = Flask(
    "Lectern",
    static_folder=STATIC_DIR,
    template_folder=TEMPLATES_DIR,
)

# ── No caching ─────────────────────────────────────────────────────────────
# Lectern is edited constantly, and a browser holding on to an old copy of a
# tool costs far more than re-fetching it. Flask's default for static files is
# a 12-hour max-age, which is how a stale build survives an edit and a reload.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0


@app.after_request
def _no_store(resp):
    if (request.path or '').startswith('/api/'):
        # Sign-in responses carry tokens: never cache them anywhere.
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp
