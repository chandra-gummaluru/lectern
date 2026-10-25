"""Lectern Flask server package.

Module map:
- core.py       Flask app instance, HTTPS and cross-site request checks, security headers
- paths.py      BASE_PATH and derived folders
- db.py         the SQLite database (accounts, sessions, versions) under LECTERN_DATA_DIR
- security.py   password hashing (argon2id), two-factor codes (TOTP), tokens, encryption, rate limits
- auth.py       accounts: sign-in, two-factor, invitations, password resets, the account API
- teams.py      teaching teams: instructors and TAs on a course offering, and what each may do
- store.py      each account's files (answering the builders' GitHub-style calls) and published pages (/p/…)
- pages.py      the page at / (splash + app), /api/config and the PWA manifest
- tools.py      the three builders, split and scoped so they share one page
- scope_css.py  prefixes a tool's CSS with its scope selector
- students.py   each offering's class list, and students signing in to its course page (email + code)
- hub.py        the course hub: an offering's course page in tabs, served from its course.json (/c/…)
- accommodations.py  accommodation requests: the students' form and its API, instructors' decisions
- classmail.py  emailing a class from Lectern, and each offering's own email settings
- mailer.py     email (invitations, password resets, security notices, students), over SMTP
- admin.py      the admin panel (/admin): its own accounts and sign-in; invitations, accounts, email settings
- cli.py        python app.py admin / setup

Course pages, grades and exams are kept on this server, in each account's own files. Only course
pages (and the files they link) are public, at /p/<handle>/…; grades and exams never are.

Entry point: ../app.py imports `app` from here.
"""
from .core import app

from .auth import auth_bp
from .pages import pages_bp
from .store import store_bp
from .teams import teams_bp
from .admin import admin_bp
from .tools import tools_bp
from .accommodations import accom_bp
from .classmail import mail_bp
from .hub import hub_bp
from .students import students_bp
from .places import places_bp

app.register_blueprint(pages_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(store_bp)
app.register_blueprint(teams_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(tools_bp)
app.register_blueprint(accom_bp)
app.register_blueprint(mail_bp)
app.register_blueprint(hub_bp)
app.register_blueprint(students_bp)
app.register_blueprint(places_bp)
