# Lectern

One web app for teaching a course: the **course page**, the **grades** and the **exams** of every course offering (a course in one term, like `csc258/f26`), in one place. It joins the Course Page Builder, the Grade Builder and the Exam Builder, and will live at **lectern.changapp.net**, served by a small Flask server laid out like Beamer+'s.

Course pages, grades and exams are kept on Lectern's server, in each person's own account. Course pages (and the files they link) are published from the server; grades and exams never are.

## A new Lectern, in one go

On a server (or your own computer), with Python 3 and git:

```
git clone https://github.com/chandra-gummaluru/lectern.git ~/apps/lectern
~/apps/lectern/new-lectern.sh
```

`new-lectern.sh` makes a Python environment (`.venv` in the folder; `LECTERN_VENV=~/venvs/cenv ./new-lectern.sh` uses one you have), installs what Lectern needs, then runs **`python app.py setup`**, which asks:

1. **Where it lives:** its public address (e.g. `https://lectern.changapp.net/`), whether HTTPS is handled in front of it (a Cloudflare Tunnel or nginx: almost always yes), its port and institution.
2. **Email** (optional): an SMTP login, and sends a test email.
3. **An admin for the admin panel:** email, name, password, and its two-factor app (a QR code right in the terminal).
4. **Old courses** (optional): imports git clones of the GitHub repositories.

It writes `.env` (readable only by you), checks that Lectern answers the way visitors will reach it (a redirect loop or a missing package shows up here, not in a browser), and says how to start it and point a tunnel at it. Run `python app.py setup` again any time to change a setting: Enter keeps each one.

Then start it with `python app.py` (under tmux or systemd on a server), sign in to the admin panel at `/admin`, and invite people, yourself included (your Lectern account is separate from your admin one).

## Run it

On your own computer, without the questions:

```
pip install -r requirements.txt
python app.py admin you@utoronto.ca
python app.py
```

Then open <http://localhost:5003/admin>, sign in as that admin, and invite yourself. Open the invitation's link to create your Lectern account: your name, the address for your course pages (e.g. `chandra` → `/p/chandra/csc258/f26/info.html`) and a password. Lectern opens at <http://localhost:5003/> (`--port` or `LECTERN_PORT` changes the port).

To try password resets without SMTP, start it with `LECTERN_PRINT_EMAILS=1`: emails are then printed to the server's log instead of sent (never do this on a real server: they carry sign-in links).

## The admin panel

At `/admin` on the same address (e.g. `https://lectern.changapp.net/admin`), with a sign-in of its own:

- **Admins aren't Lectern accounts.** They're added only on the server, and that's the only thing done there: `python app.py admin you@example.com` asks for a name and password and sets up the admin's two-factor app with a QR code in the terminal. Running it for an existing admin replaces their password and app (a forgotten password, a lost phone). A Lectern account can't open the panel, and an admin can't open courses.
- **Signing in** takes email, password and a code from the authenticator app, every time. The admin session is separate from Lectern's (its own `SameSite=Strict` cookie) and ends after 30 minutes unused (`LECTERN_ADMIN_IDLE_MINUTES`) or 12 hours.
- **In the panel:** invite people to make Lectern accounts; see every account; sign one out everywhere, let it try again after wrong passwords, turn off its two-factor sign-in (a lost phone), turn it off or back on; import old courses; turn other admins off or back on. Turning anything off needs the admin's password again.

### Moving from GitHub

Lectern used to keep everything in two GitHub repositories. On GitHub, use **Code → Download ZIP** for each, then in the admin panel's **Import Old Courses**, import each into the account it belongs to (public: course pages; private: grades and exams).

Then open each current course page in Lectern and save it, so its **Request Accommodation** buttons point at the new address. (The repositories on GitHub are left as they were; turn off GitHub Pages there when you're ready.)

## Accounts and security

- **Invite-only.** There's no public sign-up. An admin invites each person by email from the admin panel (or an instructor, to a teaching team); the link works once, for 7 days.
- **Passwords** are hashed with **argon2id** (salted, memory-hard) and never stored, logged or sent anywhere else. They travel only inside HTTPS: Lectern refuses to take a password over plain HTTP anywhere but `localhost`, and redirects HTTP to HTTPS. New passwords need at least 12 characters and can't be a very common one or contain your email or name (NIST SP 800-63B: length, not symbol rules).
- **Two-factor sign-in** (optional, recommended): any authenticator app (TOTP, RFC 6238). Each code works once. Ten one-time **recovery codes** for when the phone isn't there. Secrets are encrypted at rest (AES-256-GCM); recovery codes are stored only as keyed hashes. Swapping in a new app, or making new recovery codes, needs a current code too. An admin can turn it off for someone who lost their phone, from the admin panel.
- **Sessions** are server-side: the browser holds only a random 256-bit value in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie (`__Host-lectern`), and the server keeps only its SHA-256. A session ends after 12 hours unused or 7 days at most (`LECTERN_SESSION_IDLE_HOURS`, `LECTERN_SESSION_DAYS`), at sign-out, when the password changes (every other device) or is reset (all of them). **Your account** lists where you're signed in, and signs any of them out. If a session ends while you're working, Lectern asks you to sign in again in a window, and nothing unsaved is lost.
- **Guessing** is slowed down: each address and each email has a limit, and after 5 wrong passwords or codes in a row an account waits (30 s, then 1, 2, 4… up to 15 minutes). A browser that has signed in to the account before isn't held up by that wait, so nobody can lock you out by guessing. A wrong email and a wrong password look exactly the same (message, timing and waiting), as does "forgot password" for an email with no account.
- **Forgotten passwords:** a link by email, good for an hour, once. With two-factor on, the reset needs a code (or a recovery code) as well. Every device is signed out, and you get an email whenever your password or two-factor sign-in changes.
- **Requests** that change anything must come from Lectern's own page (a custom header, the `Origin` and `Sec-Fetch-Site` checks, and SameSite cookies), so other sites can't act as you. Lectern's pages send a strict Content-Security-Policy (no inline scripts, no framing), `X-Content-Type-Options`, `Referrer-Policy` and, over HTTPS, HSTS.
- **Your files** are yours: each account sees only its own. Every version a save replaces or deletes is kept (in `history/` on the server), so a mistake or a deleted course offering can be got back by whoever runs the server. Each account has a space limit, kept versions included (`LECTERN_QUOTA_MB`, default 2048).
- **Published course pages** (`/p/<handle>/…`) are served in a sandbox (`Content-Security-Policy: sandbox`): their scripts run, but in an origin of their own, with no access to Lectern or your session. For more separation still, serve them from another address (`LECTERN_PAGES_URL`, e.g. `https://pages.lectern.changapp.net/`, pointing at the same server's `/p/`).

## Deploying (lectern.changapp.net)

Lectern must be served over **HTTPS**. Behind nginx (or another proxy) that handles HTTPS:

1. Run it on the same machine, listening only on `127.0.0.1` (the default), e.g. `gunicorn -w 2 -b 127.0.0.1:5003 app:app` or `python app.py`. Nothing should reach it except through the proxy.
2. In nginx, pass `X-Forwarded-For $remote_addr` and `X-Forwarded-Proto $scheme`, and redirect HTTP to HTTPS.
3. In `.env` beside `app.py` (copy `.env.example`): **`LECTERN_APP_URL=https://lectern.changapp.net/`** (required: links in emails use only this address, and requests for any other host name are refused) and `LECTERN_BEHIND_PROXY=1`.
4. Fill in the `LECTERN_SMTP_…` settings (any SMTP login; for Gmail, an app password), so invitations, password resets and students' receipts are emailed.
5. `python app.py admin you@utoronto.ca`, then sign in at `/admin` and invite yourself; open the link, and turn on two-factor sign-in.

**Back up** the data folder (`LECTERN_DATA_DIR`, default `data/` beside `app.py`): `lectern.db` (accounts), `files/` (everyone's courses), `history/` (old versions) and `secret.key`. Without `secret.key` (or `LECTERN_SECRET_KEY`, if you set one), two-factor secrets and recovery codes can't be checked. The folder is in `.gitignore`: never commit it.

Other settings: `LECTERN_INSTITUTION` (under the wordmark; default "University of Toronto"), `LECTERN_LEARN_MORE` (the splash's "Learn more" link; hidden when unset), `LECTERN_MAX_UPLOAD_MB` (one save, default 64).

## Teaching teams

Each course offering has a **Teaching Team** (on its page). Its owner, the account whose files it's in, adds people by email, as:

- **Instructor:** everything the owner can do with that offering: its course page, evaluations, gradebook, exams, accommodation requests, and its team. They can't remove the owner.
- **TA:** sees the gradebook (marks, grades, students) and the evaluations and exams, and **enters marks**. A TA can't change evaluations, students, settings, exams or the course page, can't see students' accommodation requests, and can't change the team (but can leave it). The server enforces this: from a TA's save it takes only the marks (and no more than 25 cleared at once), and Lectern tells a TA before saving if anything else would be undone.

Adding someone emails them a link (or, without SMTP, shows it to send yourself). They join only once they accept: by signing in, or, new to Lectern, by making an account then and there, which is how a TA gets an account without an admin. To allow that only for your institution's addresses, set `LECTERN_TEAM_DOMAINS=utoronto.ca` (setup asks). A link works once, for 7 days, and stops working if whoever sent it leaves the team. Offerings shared with you are on your Home, marked with the owner's name and your role, at addresses like `#/~chandra/csc258/f26`.

Two people saving the same gradebook at once: the second is told it changed and can replace it or reopen it, as before. (Replacing overwrites the other's marks; reopen instead when in doubt.)

## Accommodation requests

In **Evaluations**, each evaluation has an **Accommodations** section. Its standard accommodation is its own policy for missed work (its makeups, and where its weight moves), so there's nothing to type. Choose **Students must request the standard accommodation** (it then applies only once you approve), **Students can request an alternate accommodation**, and a **Request By** date and time (the same calendar as the evaluation's date). With either kind of request on, the course page shows **Request Accommodation** beside that evaluation (in its week and in the marking scheme). Open the course page in Lectern and save it after changing these.

The button opens a form on Lectern's server (`/request?r=<your handle>&o=<course>/<term>&e=<evaluation>`). The student gives their email, identifier, first and last name; all four must match the gradebook (so the class list needs an **Email** field: Settings → fields). Then they ask for the standard accommodation or describe an alternate one, and get a receipt by email. After the request-by time, the form and the course page say the deadline has passed.

Requests go in your private files, `csc258/f26/accommodations.json`. The offering's **Accommodations** page lists them; **Approve** or **Reject** (with an optional note) saves the decision and emails the student. A student who needs something else makes another request (up to 10 per evaluation).

Optional: `LECTERN_TIMEZONE` (request deadlines; default `America/Toronto`).

## Where things are

| | Private (only you) | Public (published at `/p/<handle>/`) |
| --- | --- | --- |
| Course page | | `csc258/f26/info.html` and its linked files |
| Grades | `csc258/f26/grades.json` | |
| Exams | `csc258/f26/<exam>/exam.json` and its `.tex` files | |
| Accommodation requests | `csc258/f26/accommodations.json` | |

A course offering is the same folder in both. Only the course page and its files are public; grades and exams never are. On the server they're under `data/files/<account id>/pub` and `…/priv`.

## How it's put together

```
app.py                  python app.py: the runner (and its commands: setup, admin)
new-lectern.sh          a new Lectern: code, Python environment, requirements, then setup
server/
  core.py               the Flask app: HTTPS, cross-site request checks, security headers (no caching)
  paths.py              where things are
  db.py                 the database (SQLite, in the data folder): accounts, sessions, versions
  security.py           argon2id, two-factor codes (TOTP), tokens, encryption, rate limits
  auth.py               accounts: sign-in, two-factor, invitations, resets, /api/auth/…
  admin.py              the admin panel (/admin): admins' own sign-in; invitations, accounts, imports, /api/admin/…
  store.py              each account's files (/api/store/…, the builders' GitHub-style calls) and /p/…
  pages.py              /: the splash and the app (one page); /api/config
  accommodations.py     accommodation requests: /request (the students' form), /api/accommodations/…
  mailer.py             email (SMTP): invitations, resets, security notices, students
  cli.py                python app.py admin (adding admins: the one thing done on the server) | setup
  wizard.py             python app.py setup: the questions, .env, the first admin, the checks
  tools.py              the builders, split for sharing one page: /tools/<name>.css|.json|.js|.html
  scope_css.py          scopes a builder's CSS to its own element
templates/index.html    the splash (modelled on beamer.changapp.net) and the app's frame
templates/request.html  the students' accommodation request form (static/js/request.js, static/css/request.css)
templates/admin.html    the admin panel (static/js/admin.js, static/css/admin.css)
static/css/             splash.css (Beamer+'s tokens and layout), shell.css (top bar, path, Home)
static/js/
  scope.js              runs each builder in its own scope (see below)
  boot.js               before the first paint: splash or app
  lectern.js            the shell: Home, a course offering, the pinned path, opening builders
  auth.js               signing in (and again, mid-work), two-factor, invitations, resets
  account.js            Your account
  admin.js              the admin panel
  store.js              the calls the shell makes to your files
tools/                  the three builders, each still a single HTML file that works on its own;
                        suite.css (their shared look, kept identical in all three) and course.cls (the exam class) for reference
docs/                   the plans
tests/                  python -m pytest (server); tests/browser/ (Playwright walkthroughs against the real
                        server in its own data folder: flow_auth.py and flow_accommodations.py assert as they go)
```

**One page, each builder in its own scope.** The builders stay single files in `tools/`. The server splits each into its markup, its CSS (every rule prefixed with `[data-lt-tool="<name>"]`) and its script, wrapped so that inside it `document` and `window` are stand-ins: `getElementById` and `querySelector` look only in the builder's element, `document.body` is that element, and its key and click listeners only hear events while it's the one showing. So all three can keep their own `#stage`, `#home`, `#save`, menus and windows on one page, and a builder's unsaved work stays open while you look at another. Each builder's file ends with a short **Lectern** section: when Lectern hosts it, Lectern hands it the connection and opens files; opened on its own, it starts exactly as before (and still talks to GitHub or a folder itself). Hosted, a builder's GitHub-style calls for `lectern/pub` and `lectern/priv` go to your files on the server instead (`scope.js`), with your session.

**The top bar and path.** On Lectern's pages the bar is Home · Back/Forward · path · status · account (Save, Your account, Accounts, Sign out). Inside a builder, the builder's own bar is the top bar (its Home button goes to Lectern's Home), and the path strip sits directly under it, pinned, e.g. `Home › csc258 / f26 › Grades › Students › Castillo, Maya`. The builders' in-page paths are folded into the strip.

## Build plan

See `docs/lectern-plan.md` (and the builders' own plans beside it). Done: Lectern's own accounts (email, password, two-factor; invite-only) with everything kept on the server, replacing GitHub sign-in and folder mode; stage 1 of section 3 (shell, splash, Home, the pinned path, the builders in isolated scopes), the small fixes (section 10), the pinned path in each builder on its own, each evaluation's type, label and date in Grades (names now come from the label: Lab 1, Lab 2…), the course page's weekly layout (lectures in hour slots, a third of the row each; No class; extra hours scroll sideways; an evaluations row; older pages' lecture cards become one hour each), and the cross-links:

- **Course page ← Grades.** Opening a course page in Lectern hands it the gradebook's marking scheme (names, weights, dates, "best N of M", not-submitted rules; never students or marks). The page gets a read-only Marking scheme section (in place of a hand-made Grading table) with Edit in Grades, and each evaluation appears in the week of its date: a pill beside the week (dark for tests) and a card under the lectures. The course page owns the files and links attached to each evaluation.
- **Grades → exams and handouts.** Each evaluation has Build: it opens the evaluation's exam (a test: cover page, answer spaces) or handout (an assignment: instructions, no answer spaces), starting one named and dated the first time. The document names the evaluation it's for, and its total marks become the evaluation's out of (read-only in Grades).

Build order done through section 11. Still open: section 12.
