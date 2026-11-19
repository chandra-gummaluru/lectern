# Lectern: technical reference

The details behind Lectern: how it's set up and deployed, how accounts and security work, where files are kept, and how the code is put together. For an overview of what Lectern does, see the [README](../README.md).

## A new Lectern, in one go

On a server (or your own computer), with Python 3 and git:

```
git clone https://github.com/chandra-gummaluru/lectern.git ~/apps/lectern
~/apps/lectern/new-lectern.sh
```

`new-lectern.sh` makes a Python environment (`.venv` in the folder; `LECTERN_VENV=~/venvs/cenv ./new-lectern.sh` uses one you have), installs what Lectern needs, then runs **`python app.py setup`**, which asks:

1. **Where it lives:** its public address (e.g. `https://lectern.changapp.net/`), whether HTTPS is handled in front of it (a Cloudflare Tunnel or nginx: almost always yes), its port and institution.
2. **Email** (optional): an SMTP login, and sends a test email. (It can also be set up later, in the admin panel.)
3. **An admin for the admin panel:** email, name, password, and its two-factor app (a QR code right in the terminal).

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
- **In the panel:** invite people to make Lectern accounts; see every account; sign one out everywhere, let it try again after wrong passwords, turn off its two-factor sign-in (a lost phone), turn it off or back on, or delete it; set up email (SMTP); turn other admins off or back on. Turning anything off, deleting an account and changing the email settings need the admin's password again.
- **Deleting an account** needs its email typed out too. It signs them out, takes their course pages offline, and ends their teaching teams. Their files aren't erased: they're moved to `data/deleted/<when>-<handle>/` (with an `account.json` saying whose) for whoever runs the server to remove when sure, and their page address is never given to anyone else.
- **Email** set up in the panel is kept in the database (the SMTP password encrypted with the server's key) and used instead of `.env`'s. Saving sends a test email to the admin first; nothing is saved unless it goes through.

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

1. Run it on the same machine, listening only on `127.0.0.1` (the default), e.g. `gunicorn -w 2 -b 127.0.0.1:5003 app:app` or `python app.py`. Nothing should reach it except through the proxy. (`python app.py` is Flask's own server, fine for a small class; gunicorn copes better with a crowd.)
2. In nginx, pass `X-Forwarded-For $remote_addr` and `X-Forwarded-Proto $scheme`, and redirect HTTP to HTTPS.
3. In `.env` beside `app.py` (copy `.env.example`): **`LECTERN_APP_URL=https://lectern.changapp.net/`** (required: links in emails use only this address, and requests for any other host name are refused) and `LECTERN_BEHIND_PROXY=1`.
4. Fill in the `LECTERN_SMTP_…` settings (any SMTP login; for Gmail, an app password), so invitations, password resets and students' receipts are emailed.
5. `python app.py admin you@utoronto.ca`, then sign in at `/admin` and invite yourself; open the link, and turn on two-factor sign-in.

**Back up** the data folder (`LECTERN_DATA_DIR`, default `data/` beside `app.py`): `lectern.db` (accounts), `files/` (everyone's courses), `history/` (old versions) and `secret.key`. Without `secret.key` (or `LECTERN_SECRET_KEY`, if you set one), two-factor secrets and recovery codes can't be checked. The folder is in `.gitignore`: never commit it.

**Embedding a course page in Quercus:** in a Quercus page's HTML editor, `<iframe src="https://lectern.changapp.net/c/<handle>/<course>/<term>/" width="100%" height="900" style="border:0"></iframe>`. Course pages (`/c/…`) may be framed by `https://q.utoronto.ca` and `https://utoronto.instructure.com` (`LECTERN_EMBED_FROM` replaces that list); Lectern's own pages can't be framed anywhere. Inside the frame, the public parts work; signing in (for the Enrolled parts) needs the page opened on its own, since browsers don't send Lectern's cookie inside another site's frame.

**Heavy traffic.** Lectern limits how often each person (and each address) can sign in, ask for codes, post, vote and send requests, and it runs at most `LECTERN_PASSWORD_SLOTS` (default 4) password checks at once: each takes 64 MiB, so a flood of sign-in tries can't use up the server's memory (beyond that, people are asked to try again in a moment). These limits are kept in memory, so a restart resets them (students' daily code caps are in the database and survive it). Behind a Cloudflare Tunnel, the server's own address stays hidden and Cloudflare absorbs floods; for a further layer, add a Cloudflare rate-limiting rule for `/api/auth/` and `/api/admin/login` (e.g. 20 requests a minute per address).

Other settings: `LECTERN_INSTITUTION` (under the wordmark; default "University of Toronto"), `LECTERN_LEARN_MORE` (the splash's "Learn more" link; hidden when unset), `LECTERN_MAX_UPLOAD_MB` (one save, default 64).

## Teaching teams

Each course offering has a **Teaching Team** (on its page). Its owner, the account whose files it's in, adds people by email, as:

- **Instructor:** everything the owner can do with that offering: its course page, evaluations, gradebook, exams, accommodation requests, and its team. They can't remove the owner.
- **TA:** sees the gradebook (marks, grades, students) and the evaluations and exams, and **enters marks**. A TA can't change evaluations, students, settings, exams or the course page, can't see students' accommodation requests, and can't change the team (but can leave it). The server enforces this: from a TA's save it takes only the marks (and no more than 25 cleared at once), and Lectern tells a TA before saving if anything else would be undone.

Adding someone emails them a link (or, without SMTP, shows it to send yourself). They join only once they accept: by signing in, or, new to Lectern, by making an account then and there, which is how a TA gets an account without an admin. To allow that only for your institution's addresses, set `LECTERN_TEAM_DOMAINS=utoronto.ca` (setup asks). A link works once, for 7 days, and stops working if whoever sent it leaves the team. Offerings shared with you are on your Home, marked with the owner's name and your role, at addresses like `#/~chandra/csc258/f26`.

Two people saving the same gradebook at once: the second is told it changed and can replace it or reopen it, as before. (Replacing overwrites the other's marks; reopen instead when in doubt.)

## Accommodation requests

In **Evaluations**, each evaluation has an **Accommodations** section. Its standard accommodation is its own policy for missed work (its makeups, and where its weight moves), so there's nothing to type. Choose **Students must request the standard accommodation** (it then applies only once you approve), **Students can request an alternate accommodation**, and a **Request By** date and time (the same calendar as the evaluation's date). With either kind of request on, the course page shows **Request Accommodation** beside that evaluation (in its week and in the marking scheme). The course page has them once the gradebook is saved.

Students ask on the course page itself, signed in with the code it emails them (so only the student can ask in their own name). They also give their identifier, first and last name, which must match the class list. Then they ask for the standard accommodation or describe an alternate one; it's listed in My Requests on the course page. After the request-by time, the course page says the deadline has passed.

Requests go in your private files, `csc258/f26/accommodations.json`. The offering's **Accommodations** page lists them; **Approve** or **Reject** (with an optional note) saves the decision and emails the student. A student who needs something else makes another request (up to 10 per evaluation).

Optional: `LECTERN_TIMEZONE` (request deadlines; default `America/Toronto`).

## The course hub

Each offering's course page is served by Lectern in tabs at `/c/<handle>/<course>/<term>/`: **This week** (it opens here), **Announcements**, **Activities**, **Evaluations**, **About** and **My accommodations**.

- **Nothing is made on the course page itself.** Each part of it comes from a part of the offering in Lectern, read live: Activities (`lectures.json`), Announcements (`announcements.json`, each in the week of its date), Evaluations (the gradebook: weights, dates, files and links), the Teaching Team (each person's activities, office hours and contact details: `team.json`), and the title and description (`about.json`), which are under the course code on the offering's page. The code, term and school are the offering's (its folder, and `LECTERN_INSTITUTION`). About shows the description, the teaching team, and the gradebook's course rules that its **Grade Settings** choose to show.
- **View Course Page** (the offering's page, top right) opens it in Lectern: a preview (**Preview** shows a visitor's view), a link to the live page, and **each tab public or signed-in only** (the globe or lock beside its name; save to keep it). My accommodations is always signed-in only. A visitor's This week only shows what's on tabs they can see.
- It's saved as `course.json` (an older page, only `info.html`, opens and becomes one when saved). Its published address (`/p/<handle>/<course>/<term>/` or `…/info.html`) leads to the hub once it has a `course.json`, and `course.json` itself is never served from `/p/`.
- **Signed in** means the offering's owner and teaching team (their Lectern accounts), and its students: each signs in to that course's page with their email and a one-time code it emails them (the course page's own **Sign in**, `/c/<handle>/<course>/<term>/sign-in`). That needs email set up on the server. Staff see a bar on the hub with **See it as a visitor** (`?as=public`).

## Students

- **The offering's Students card is the class list**, under the Teaching Team on its page: add students one at a time or import a class list (a CSV from Quercus or ACORN), drop or remove them, and email them the course page's link. It's the gradebook's students (`grades.json`): the gradebook shows them for marks, but students are added and changed only here. A student with marks or notes is dropped (kept), not deleted.
- **What each student has** (the identifier's name, the email domain, and any other fields such as UTORid) is set in the card before the first student is added, and fixed from then on.
- **Every student has an email**, at the domain set there (e.g. `mail.utoronto.ca`): it's how they sign in. The card and the gradebook say who's missing one.
- Each enrolled student (not dropped) with an email can sign in; the card shows who has, and who's been sent the link.
- **Each offering can have its own email settings** (no screen for them now that Email the Class is gone; the API is still there, `server/classmail.py`): any SMTP login, e.g. a course address as the sender. Saving sends you a test first; nothing is saved unless it goes through. They're kept on the server (not in the gradebook, which TAs can read), the password encrypted with the server's key and never shown again. Without them, Lectern's own email (the admin panel's, or `.env`'s) is used. The offering's accommodation emails and sign-in codes use them too.

## My Marks, and the grade so far

- A signed-in student's marks come in the course page's API (`viewer.marks`, `server/hub.py`), only for evaluations the gradebook has **released**. The course page shows each on its evaluation's page and all of them on **My Marks** (`#marks`, `static/js/hub.js`).
- **Grade so far** (`viewer.sofar`) is there only when the gradebook's Settings turn it on (`policies.show.sofar`). `server/grading.py` works it out exactly as the gradebook does (the Grade Builder's `studentResult`: makeups, reweighting, best N of M, the student's own accommodations), from the released marks only, so an unreleased mark counts as not marked yet. The final rules (ranges, rounding, automatic fail) aren't applied. `tests/test_grading.py` runs the builder's own JavaScript with node on the sample gradebooks (and randomized versions of them) and checks both agree, so **a change to `studentResult` needs the same change in `grading.py`**.

## Export, Import and the demo course

`server/transfer.py`.
- **Export** (an offering's page, instructors only): a `.zip` with `lectern-export.json`, then `pub/` and `priv/` holding the offering's files relative to its folder. Left out: the gradebook's students, marks, accommodations (`overrides`), set grades (`finals`) and released flags; `accommodations.json`, `announcements.json` and `team.json`; who runs each section in `groups.json` (those are this server's accounts). Discussions, attendance and sign-ins are in the database and never go.
- **Import** (Home): reads the manifest first (`/import/peek`), then brings the files in as a new offering of yours under any course and term you don't have, leaving the same things out again (a file can be made by hand). **Move its dates** shifts every date by whole weeks, from the first Monday of the old term to the new one's, so each keeps its weekday: ISO dates and announcement stamps in the JSON files (whole strings only, so links are left alone), each week's dates text, and the long dates and term name in exams (`exam.json` and the `.tex` files). Uploads up to `LECTERN_MAX_UPLOAD_MB`.
- **The demo course** (Home): `sample-data/demo-course`, a generic made-up course (DEMO101, A Sample Course, written for Fall 2026), loaded as `demo101` in the current term with the same date move. Its students get `@example.com` emails (which take no mail), the marks of the evaluations whose dates have passed are kept and released, and Grade So Far is on.

## Marking scanned exams

`server/autograde/` marks printed exams from their scans: multiple choice, true or false, multiple answers, number boxes, fractions and rows of cells, and finds whose exam it is from the cover's student-number boxes. Each exam's **Print and Scan** page (`static/js/scans.js`, `#/<course>/<term>/scans/<exam>`, from the Exam Builder's top bar; `server/scanning.py`, `/api/scans…`) does it all in Lectern:

- **Print.** The server compiles the exam's saved `.tex` files with pdflatex: the student copy, answer key and marking guide, per version. LaTeX runs as a guest: `-no-shell-escape`, `openin_any=p` and `openout_any=p` (it reads and writes only in its own temporary folder: no absolute paths, no `..`), and limits on time and file size; `tests/test_scanning.py` checks it can't read `/etc/hostname`. PDFs are cached by what they're made from (`data/latex/cache`, 14 days; LaTeX's own font caches in `data/latex/var`). The owner's or a coordinator's download of the student copy is kept as the **printed copy**, and scans are marked against it, so an exam changed after printing still marks right (the page says when it has changed). Settings: `LECTERN_LATEX_AT_ONCE` (compiles at once, default 2).
- **Scans.** Uploaded one file at a time (PDFs or images, up to `LECTERN_MAX_SCAN_MB`, default 1024). Each upload starts the grader in a background thread by itself (`_start_mark`; an upload while it's marking is picked up by another pass when it's done, in `_mark_job`); `job.json` has its progress, with a heartbeat: a server restart shows it stopped. Pages are put together into booklets by where they are in the uploads, unless they're from **numbered booklets**: printed from the Exam Builder's Student Copy (`/api/scans/pdf?print=1&booklets=N`, numbers carrying on from the last printed, kept in `printed.json`), `autograde/numbered.py` draws each booklet's number into its pages' QR codes (`LECTERN|<code>|<page>|<booklet>`, as squares over the student copy's own pages, no LaTeX run per copy), and `grade.booklets` puts those pages together by their number wherever they are, in any upload (it remembers where each page is on the way through and lines them up a booklet at a time after). A numbered booklet's name in `review.json` is its code and number, so pages uploaded later keep its review. Each booklet lists the template pages it's `missing`, and the page shows how many booklets are whole of how many wrote it (`wrote`: the evaluation's attendance if it was taken, else the class). Who marks each question is `graders.json` ({label: [user id]}, set by the owner or a coordinator with `/api/scans/graders`): a TA sees and can mark only theirs and the ones nobody is on (`_mine`). The Scans part is drawn on the evaluation's page in Grades (`scansPage` with `into`, mounted by `Lectern.fillScans`).
- **Review.** Each booklet: its cover (whose it is: confirm or pick from the class list), and every question with a picture of the answer, what was read, the answer and its score. A person's scores and choices are kept in `review.json`, apart from the grader's `results.json`, so marking again (more scans) keeps them (booklets are known by their scanned pages).
- **Send.** Each finished booklet (student known, every question marked or checked) becomes the student's mark for the exam's evaluation (`settings.link`), written into `grades.json` by the server. Marks that differ from what's there are listed and replaced only when asked.
- **Who.** Anyone on the teaching team sees the page and the PDFs; the owner and coordinators print the copy that's marked against, upload, mark and delete; they and TAs review and send marks.
- **Where.** `data/scans/<owner id>/<course>/<term>/<exam>/` (`printed/`, `uploads/`, `pictures-<when>/`, `results.json`, `review.json`): outside the offering's files, so students' scans aren't versioned, exported or counted in the account's space. **Delete the scans and results** removes the folder; deleting an account moves it with the account's files.

The grader can also be run by hand, without Lectern's page:

1. **In the Exam Builder**, Settings › Pages › **Marking from scans**. The student copy then gets a black square near each corner and a QR code at the top left of every page (`LECTERN|<course-term-exam[-version]>|<page>`), and every answer piece gets an invisible tag in the PDF giving where it is (`\ScanCode` and `\ScanID` in `course.cls` v2.6; the answer key and marking guide get none of it). Compile the student copy as usual and print that PDF.
2. **Scan** the written exams, whole booklets one after another, any page order within a booklet, either way up.
3. **Mark:**

   ```
   pip install -r requirements-scan.txt
   python app.py autograde exam.json --pdf midterm.pdf --scans scans.pdf --class grades.json --out results
   ```

   One `--pdf` per version (the printed student copies), any number of `--scans` (PDFs or images), and the offering's gradebook for its class list. It writes `results/review.html` (each booklet, a picture of every answer, what was read, the ones to look at), `marks.csv` and `results.json`.

How it reads a page: the QR code says which exam, version and page it is; the corner squares line the scan up with the printed page, so every tagged piece is at known pixels; the printed ink (outlines, labels) is taken away, leaving the student's. A bubble is filled from a quarter of its inside, a check box is ticked from a little ink. Handwriting is split into characters and each is read by a small convolutional network run in numpy (`digits.py`, weights in `digits.npz`, made by `train_digits.py` with TensorFlow from MNIST's 60,000 digits, digits and symbols in handwriting-like fonts, and scribbles): a digit, or "something else" ($, %, a letter), read as `?`. Every character is first thinned to its skeleton and drawn again at one width, so a fine pen and a felt tip look alike to it. The student's ink is found by hysteresis (pale ink counts when it joins clearly dark ink), and each box is read twice, strictly and loosely, keeping the surer reading: light strokes stay whole and blurry ones stay thin. Its probabilities are softened (a temperature of 2) and averaged over the character shifted a pixel each way, so a wrong reading is rarely also a sure one. On MNIST's test digits: 98% right as drawn, 95% as a pen and scanner leave them. The student is the class-list number that best fits the cover's digits, matched without a person only when the next likeliest student is about 400 times less likely.

Each question comes back **marked**, **check** (marked, but a person should look: two bubbles filled, unsure handwriting, a wrong number in a question with room for working), **mark by hand** (written answers, blanks and boxes with words) or **page missing**. Handwriting is careful on purpose: a reading that matches the answer is trusted, but one that doesn't is marked wrong only when every digit is clear and the right answer is an unlikely reading of the same ink; anything else is a check, which asks "Is this what it says?" (Yes, or No and type what it says: the score follows). A mark that surely isn't a digit at either end ($30, 30 cm) is left out when the rest is right. Any reading can be clicked and corrected; for bubbles, the options are buttons. A booklet whose student isn't matched shows as "Unmatched, Student 1" (XXXXXXXXXX) until someone picks the student. Multiple answers is all or nothing; answer pieces in one question share its marks.

`tests/test_autograde.py` makes an exam with the builder's own LaTeX code, compiles it, writes answers on its pages (held-out handwritten digits the network never saw), "scans" them (turned, scaled, blurred, speckled, out of order, upside down) and checks the results. On 210 such booklets (half of them in a thin pen, numbers sometimes written with a $): no student matched wrongly, nearly every bubble read right, no handwriting marked wrong without a flag; about a third of handwritten answers, mostly the wrong ones, go to a check. Real pens and scanners will differ: look at the first real batch closely.

## Where things are

| | Private (only you) | Public (published at `/p/<handle>/`) |
| --- | --- | --- |
| Course page | | `csc258/f26/info.html` and its linked files |
| Grades | `csc258/f26/grades.json` | |
| Exams | `csc258/f26/<exam>/exam.json` and its `.tex` files | |
| Scanned exams | `data/scans/<account id>/csc258/f26/<exam>/` (outside the files: scans, results, the printed copy) | |
| Accommodation requests | `csc258/f26/accommodations.json` | |

A course offering is the same folder in both. Only the course page and its files are public; grades and exams never are. On the server they're under `data/files/<account id>/pub` and `…/priv`.

## How it's put together

```
app.py                  python app.py: the runner (and its commands: setup, admin, autograde)
new-lectern.sh          a new Lectern: code, Python environment, requirements, then setup
requirements.txt        the server's Python packages (requirements-dev.txt: pytest, Playwright; requirements-scan.txt: marking scans)
server/                 the Flask server (one module per area; each starts with what it does)
  core.py               the Flask app: HTTPS, cross-site request checks, security headers (no caching)
  paths.py              where things are
  db.py                 the database (SQLite, in the data folder): accounts, sessions, versions, students
  security.py           argon2id, two-factor codes (TOTP), tokens, encryption, rate limits
  auth.py               Lectern accounts: sign-in, two-factor, invitations, resets, /api/auth/…
  admin.py              the admin panel (/admin): its own sign-in; invitations, accounts, email settings
  cli.py, wizard.py     python app.py admin | setup (the questions, .env, the first admin, the checks)
  store.py              each account's files (/api/store/…, the builders' GitHub-style calls) and /p/…
  pages.py              /: the splash and the app (one page); /api/config
  tools.py, scope_css.py  the builders, split to share one page: /tools/<name>.css|.json|.js|.html
  teams.py              teaching teams: members, roles, invitations
  hub.py                the course page (/c/<handle>/<course>/<term>/) and its API (/api/hub/…)
  students.py           each offering's class list, and students signing in to its course page
  accommodations.py     accommodation and remark requests (from the signed-in course page) and decisions
  discuss.py            discussions on the course page
  attendance.py         attendance at a test (ID cards read by a phone's camera)
  places.py             finding a building or address for a Where
  classmail.py          emailing a class, and each offering's own email settings (/api/mail/…)
  mailer.py             email (SMTP)
  autograde/            marking scanned exams (python app.py autograde): layout, scan, read, digits, grade, report
  scanning.py           an exam's Print and Scan page: PDFs (pdflatex), scans, marking them, review, marks to the gradebook
templates/              index.html (the splash and the app), admin.html, hub.html and hub-signin.html (the course page)
static/css/             splash.css, shell.css (Lectern), hub.css (the course page), admin.css
static/js/              one file per page or part, each starting with what it is. The main ones:
  lectern.js            the shell: Home, a course offering, the pinned path, opening builders
  scope.js              runs each builder in its own scope (see below)
  hub.js, hub-view.js   the course page (hub-view.js is its look, shared with the Course Page Builder)
  scans.js              an exam's Print and Scan page: its PDFs, scans, the grader's results, reviewing a booklet
  sw.js                 the service worker that makes Lectern installable as an app (Install Lectern, in the
                        account menu); it caches nothing, and only shows "You're offline" when the server can't be reached
static/vendor/          Tesseract (reading ID cards in the browser), with its licences
tools/                  the three builders, each still a single HTML file that works on its own;
                        suite.css (their shared look, kept identical in all three) and course.cls (the exam class: the
                        Exam Builder carries a copy, COURSE_CLS, which must stay identical; a test checks)
docs/                   ui-patterns.md (named UI patterns to follow); archive/ (the early build plans)
sample-data/            made-up courses and a class list, for trying Lectern and for the tests
tests/                  python -m pytest (the server); tests/browser/ (Playwright walkthroughs: see its README)
```

**One page, each builder in its own scope.** The builders stay single files in `tools/`. The server splits each into its markup, its CSS (every rule prefixed with `[data-lt-tool="<name>"]`) and its script, wrapped so that inside it `document` and `window` are stand-ins: `getElementById` and `querySelector` look only in the builder's element, `document.body` is that element, and its key and click listeners only hear events while it's the one showing. So all three can keep their own `#stage`, `#home`, `#save`, menus and windows on one page, and a builder's unsaved work stays open while you look at another. Each builder's file ends with a short **Lectern** section: when Lectern hosts it, Lectern hands it the connection and opens files; opened on its own, it starts exactly as before (and still talks to GitHub or a folder itself). Hosted, a builder's GitHub-style calls for `lectern/pub` and `lectern/priv` go to your files on the server instead (`scope.js`), with your session.

**The top bar and path.** On Lectern's pages the bar is Home · Back/Forward · path · status · account (Save, Your account, Accounts, Sign out). Inside a builder, the builder's own bar is the top bar (its Home button goes to Lectern's Home), and the path strip sits directly under it, pinned, e.g. `Home › csc258 / f26 › Grades › Students › Castillo, Maya`. The builders' in-page paths are folded into the strip.

## How the builders connect

- **Course page ← Grades.** Opening a course page in Lectern hands it the gradebook's marking scheme (names, weights, dates, "best N of M", not-submitted rules; never students or marks). The page gets a read-only Marking scheme section (in place of a hand-made Grading table) with Edit in Grades, and each evaluation appears in the week of its date: a pill beside the week (dark for tests) and a card under the lectures. The course page owns the files and links attached to each evaluation.
- **Grades → exams and handouts.** Each evaluation has Build: it opens the evaluation's exam (a test: cover page, answer spaces) or handout (an assignment: instructions, no answer spaces), starting one named and dated the first time. The document names the evaluation it's for, and its total marks become the evaluation's out of (read-only in Grades).

The plans Lectern was built from (GitHub-era: before Lectern kept everything on its own server) are in `docs/archive/`.
