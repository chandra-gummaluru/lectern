# Lectern

One web app for teaching a course: the **course page**, the **grades** and the **exams** of every course offering (a course in one term, like `csc258/f26`), in one place. It joins the Course Page Builder, the Grade Builder and the Exam Builder, and will live at **lectern.changapp.net**, served by a small Flask server laid out like Beamer+'s.

Nothing but sign-in passes through the server. Course pages, grades and exams go straight from the browser to GitHub (or to a folder on your computer).

## Run it

```
pip install -r requirements.txt
python app.py
```

Then open <http://localhost:5002/>. (`--port` changes the port.)

- **Choose a folder** works straight away in Chrome or Edge: pick the folder that holds both repositories side by side (e.g. `courses/` and `courses-private/`, your git clones). Course pages, grades and exams all open and save there; commit and push with git as usual.
- **Sign in with GitHub** needs the GitHub App (below). Copy `.env.example` to `.env` beside `app.py` and fill in its Client ID, client secret and slug; `python app.py` reads it. (`.env` is in `.gitignore`: the secret is never committed.)

Other settings: `LECTERN_APP_URL` (the public address, e.g. `https://lectern.changapp.net/`; when unset, whatever address the browser used), `LECTERN_INSTITUTION` (under the wordmark; default "University of Toronto") and `LECTERN_LEARN_MORE` (the splash's "Learn more" link; hidden when unset).

## The GitHub App (one-time)

1. Go to **GitHub → Settings → Developer settings → GitHub Apps → New GitHub App** (<https://github.com/settings/apps/new>).
2. **GitHub App name:** `Lectern`. Names are unique across all of GitHub; if it's taken, use something like `Lectern UofT` (the app itself still says Lectern).
3. **Homepage URL:** `https://lectern.changapp.net`
4. **Callback URL:** `https://lectern.changapp.net/api/github/callback`. Click **Add Callback URL** and add `http://localhost:5002/api/github/callback` too, for running it on your computer.
5. Leave **Expire user authorization tokens** ticked (sign-ins last 8 hours and renew themselves). Leave **Request user authorization (OAuth) during installation** and **Enable Device Flow** unticked.
6. **Webhook:** untick **Active**.
7. **Permissions → Repository permissions:** **Contents**, **Administration** and **Pages**, each **Read and write**. (Metadata becomes read-only by itself.) No account or organization permissions.
8. **Where can this GitHub App be installed?** **Any account**, so anyone can sign in with their own GitHub account and use their own repositories. **Create GitHub App.** (An app made with "Only on this account" can be switched later: Advanced → Make public.)
9. On the app's page: copy the **Client ID**, then **Generate a new client secret** and copy it (it's shown once). Put both in the environment as above. The app's address, `github.com/apps/<slug>`, gives `LECTERN_GH_APP_SLUG`.
10. **Install App** (left menu) → your account → **All repositories** (so Lectern can create the public repository), or **Only select repositories** with your private repository and the public one.

Anyone else does the same from their side: they sign in with GitHub, and Lectern's repository page offers **Install Lectern on GitHub**, where they pick which of their repositories it may use. Their tokens stay in their browser; only the sign-in passes through the server. Optionally set the app's **Setup URL** to `https://lectern.changapp.net/` so GitHub sends people back to Lectern after installing.

Then **Sign in with GitHub**, pick your private repository, and Lectern pairs it by name: `<name>-private` (private) goes with `<name>` (public), e.g. `courses-utor-private` and `courses-utor`. It offers to create the public one (public, with GitHub Pages on) if it doesn't exist.

## Repositories

| | Private (`<name>-private`, e.g. `courses-utor-private`) | Public (`<name>`, e.g. `courses-utor`, GitHub Pages) |
| --- | --- | --- |
| Course page | | `csc258/f26/info.html` and its linked files |
| Grades | `csc258/f26/grades.json` | |
| Exams | `csc258/f26/<exam>/exam.json` and its `.tex` files | |

A course offering is the same folder in both. Only the course page and its files are public; grades and exams never are.

## How it's put together

```
app.py                  python app.py: the development runner
server/
  core.py               the Flask app (no caching)
  paths.py              where things are
  pages.py              /: the splash and the app (one page)
  login.py              Sign in with GitHub: /api/github/config, /callback, /refresh
  tools.py              the builders, split for sharing one page: /tools/<name>.css|.json|.js|.html
  scope_css.py          scopes a builder's CSS to its own element
templates/index.html    the splash (modelled on beamer.changapp.net) and the app's frame
static/css/             splash.css (Beamer+'s tokens and layout), shell.css (top bar, path, Home)
static/js/
  scope.js              runs each builder in its own scope (see below)
  lectern.js            the shell: sign-in, Home, a course offering, the pinned path, opening builders
  github.js             sign-in tokens, refresh, the GitHub calls Lectern makes itself
  folder.js             folder mode
tools/                  the three builders, each still a single HTML file that works on its own;
                        suite.css (their shared look, kept identical in all three) and course.cls (the exam class) for reference
docs/                   the plans
tests/                  python -m pytest (server); tests/browser/ (Playwright walkthroughs, see inside)
```

**One page, each builder in its own scope.** The builders stay single files in `tools/`. The server splits each into its markup, its CSS (every rule prefixed with `[data-lt-tool="<name>"]`) and its script, wrapped so that inside it `document` and `window` are stand-ins: `getElementById` and `querySelector` look only in the builder's element, `document.body` is that element, and its key and click listeners only hear events while it's the one showing. So all three can keep their own `#stage`, `#home`, `#save`, menus and windows on one page, and a builder's unsaved work stays open while you look at another. Each builder's file ends with a short **Lectern** section: when Lectern hosts it, Lectern hands it the connection and opens files; opened on its own, it starts exactly as before.

**The top bar and path.** On Lectern's pages the bar is Home · status · account · Save. Inside a builder, the builder's own bar is the top bar (its Home button goes to Lectern's Home), and the path strip sits directly under it, pinned, e.g. `Home › csc258 / f26 › Grades › Students › Castillo, Maya`. The builders' in-page paths are folded into the strip.

## Build plan

See `docs/lectern-plan.md` (and the builders' own plans beside it). Done: stage 1 of section 3 (shell, splash, Home, the pinned path, the builders in isolated scopes, sign-in and the two repositories), the small fixes (section 10), the pinned path in each builder on its own, each evaluation's type, label and date in Grades (names now come from the label: Lab 1, Lab 2…), the course page's weekly layout (lectures in hour slots, a third of the row each; No class; extra hours scroll sideways; an evaluations row; older pages' lecture cards become one hour each), and the cross-links:

- **Course page ← Grades.** Opening a course page in Lectern hands it the gradebook's marking scheme (names, weights, dates, "best N of M", not-submitted rules; never students or marks). The page gets a read-only Marking scheme section (in place of a hand-made Grading table) with Edit in Grades, and each evaluation appears in the week of its date: a pill beside the week (dark for tests) and a card under the lectures. The course page owns the files and links attached to each evaluation.
- **Grades → exams and handouts.** Each evaluation has Build: it opens the evaluation's exam (a test: cover page, answer spaces) or handout (an assignment: instructions, no answer spaces), starting one named and dated the first time. The document names the evaluation it's for, and its total marks become the evaluation's out of (read-only in Grades).

Build order done through section 11. Still open: section 12.
