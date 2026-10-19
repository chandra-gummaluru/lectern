"""Lectern Flask server package.

Module map:
- core.py       Flask app instance (+ no-cache headers)
- paths.py      BASE_PATH and derived folders
- pages.py      the page at / (splash + app) and the PWA manifest
- login.py      Sign in with GitHub (a GitHub App's user login): config, callback, refresh
- tools.py      the three builders, split and scoped so they share one page
- scope_css.py  prefixes a tool's CSS with its scope selector

Nothing but sign-in passes through the server: course pages, grades and exams go
straight from the browser to GitHub (or to a folder on this computer).

Entry point: ../app.py imports `app` from here.
"""
from .core import app

from .login import login_bp
from .pages import pages_bp
from .tools import tools_bp

app.register_blueprint(pages_bp)
app.register_blueprint(login_bp)
app.register_blueprint(tools_bp)
