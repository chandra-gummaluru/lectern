"""Lectern Flask server package.

Module map:
- core.py       Flask app instance (+ no-cache headers)
- paths.py      BASE_PATH and derived folders
- pages.py      the page at / (splash + app) and the PWA manifest
- login.py      Sign in with GitHub (a GitHub App's user login): config, callback, refresh
- tools.py      the three builders, split and scoped so they share one page
- scope_css.py  prefixes a tool's CSS with its scope selector
- accommodations.py  accommodation requests: the students' form and its API, instructors' decisions
- ghapp.py      the GitHub App acting as itself (for students, who don't sign in)
- mailer.py     email to students, over SMTP

Course pages, grades and exams go straight from the browser to GitHub (or to a folder
on this computer). The server handles sign-in, and accommodation requests: students
aren't signed in, so it reads the class list and records their requests as the GitHub App.

Entry point: ../app.py imports `app` from here.
"""
from .core import app

from .login import login_bp
from .pages import pages_bp
from .tools import tools_bp
from .accommodations import accom_bp

app.register_blueprint(pages_bp)
app.register_blueprint(login_bp)
app.register_blueprint(tools_bp)
app.register_blueprint(accom_bp)
