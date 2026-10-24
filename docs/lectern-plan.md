# Lectern — Build Plan (agreed Oct 17 2026)

One web app at **lectern.changapp.net** that merges the Course Page Builder, Grade Builder and Exam Builder. Hosted on the changapp.net Flask server (same setup as Beamer+).

## 1. Name, hosting, sign-in
- Name: **Lectern** (splash screen, top bar, GitHub App name).
- Address: `lectern.changapp.net`.
- Sign in with a GitHub App (user login). Server blueprint `courses_login.py` (already written): update `COURSES_APP_URL` to `https://lectern.changapp.net`; callback `https://lectern.changapp.net/api/github/callback`; refresh at `/api/github/refresh`.
- Chandra registers the GitHub App himself (Claude supplies exact steps): permissions Contents, Administration, Pages (read and write).

## 2. Repositories
- Chandra picks one **private** repo (e.g. `courses`): exams and grades.
- The **public** repo has the plain name (`courses-utor`): course pages and linked files, GitHub Pages; the private one is the same name + `-private` (`courses-utor-private`). Lectern creates the public one if missing (public, Pages on). (Decided Oct 18; was `<name>` + `-shared`.)
- Local-folder mode: pick a parent folder holding both repos.
- No rename needed: `courses-utor` stays the public repo (its Pages URLs don't change), paired with `courses-utor-private`.
- Private repo layout mirrors the public one: `csc258/f26/grades.json`, `csc258/f26/<exam>/exam.json` (a course offering is the same folder in both repos). Ask whether existing exams/grades need moving in.

## 3. App structure
- Organised by **course offering** (`csc258/f26`), each with Course page · Grades · Exams.
- One top bar: Home · status · Save (dark).
- Build stages: (1) shell + shared Home + navigation, tools in isolated scopes; (2) merge GitHub connection, save dialog, menus, undo; (3) cross-links (sections 6–8).

## 4. Splash screen
- Modelled on beamer.changapp.net: centred name **Lectern**, "University of Toronto", one-line tagline, two buttons (**Choose a folder**, **Sign in with GitHub**), "Learn more" link.
- **Open:** screenshot of beamer.changapp.net to match fonts, colours, spacing.

## 5. Navigation path (all three tools now, and Lectern)
- The path sits in its **own strip directly under the top bar, outside the white box**, pinned (sticky) while the page scrolls. Clicking any part never moves it.
- **Always present**, including Home (shows "Home"); e.g. `Home › csc258 / f26 › Grades › Students › Castillo, Maya`.
- Keep per-page scroll memory (`goPage`).

## 6. Evaluations: Grades is the single source
- Each evaluation gets:
  - **Type**: only **Test** or **Assignment**.
    - Test: written at a set time and place; has a date and time.
    - Assignment: handout worked on in own time, submitted by a deadline; has a due date.
  - **Label**: free text (Lab, Quiz, Project, Midterm…). Numbering follows the label (Lab 1, 2, 3 separate from Assignment 1, 2).
  - **Date** (test date/time or assignment due date) — new field.
- Grades owns what the evaluation *is*: name, label, type, weight, date, policies.

## 7. Course page reads from Grades
- **Marking scheme** section built automatically from Grades (names, weights, policies such as "best 3 of 4"). Read-only, with **Edit in Grades** links.
- Each evaluation appears automatically in the right week's **evaluations row** and as a deadline pill (dark for tests, light for assignments). Read-only except attachments.
- Course page owns what students *get*: files and links (handout, submission link) attached to each evaluation.
- Only the scheme is copied to the public page; never student data.

## 8. Builder link (Exam Builder → exam and handout builder)
- Every evaluation in Grades has a **Build** button opening the builder with a linked document, pre-named and dated.
- Type sets the format: Test → exam layout (cover page, answer spaces); Assignment → handout layout (instructions, no answer boxes).
- The document owns the questions and **total marks**; the total flows into Grades (never entered twice).
- Marks are entered as **totals only** in Grades (no per-question marks).

## 9. Course page: weekly layout
- **Lecture row**: hour slots, default **3 per week**, adjustable per week for extra hours.
  - A lecture card spans 1, 2 or 3+ hours; width proportional to hours. Every hour is always **one third of the row width**, so weeks line up all term.
  - Weeks with more than 3 hours **scroll sideways**, with a soft fade and small arrow at the edge.
  - Empty slots: **blank space** for students; dashed "+ Add lecture" while editing.
  - A slot can be marked **"No class"** (holidays).
  - Editor stops a card from exceeding the week's hours.
  - Each card holds any number of files and links.
- **Evaluations row** underneath (from Grades, section 7). Not tied to lectures; link in a description if needed.
- Phones: cards stack full width.
- Existing CSC258 and CSC108 pages: current lecture cards migrate automatically as one hour each.

## 10. Small fixes
- Course Page Builder: replace remaining "card" wording to match "Files and links" ("+ Add file or link", counts, "Untitled", delete/move text).
- Grade Builder: drop the "80% marked" figure in the bottom bar.
- Grade Builder: grades under 50% no longer red.
- Live Course Page Builder copy is the Oct 17 file (`course-page-builder_5.html`); no re-patching needed.

## 11. Suggested build order (tomorrow onward)
1. Small fixes (section 10) and pinned navigation path in all three tools.
2. Evaluation type, label and date in Grades.
3. Course page weekly layout (lecture slots, evaluations row, migration).
4. Lectern shell: splash, Home, navigation, sign-in, repos.
5. Cross-links: marking scheme and evaluations from Grades; Build button and totals.

## 12. Still open
- Decided Oct 18: existing exams/grades files don't need moving into the private repo for now.
- Decided Oct 18: exams keep the Exam Builder's layout, `<course>/<term>/<exam>/exam.json` (no `exams/` subfolder), so Lectern and the builder stay consistent.
- Beamer+ screenshot for the splash.
- Not yet in Grades: letter grade scales beyond ranges, Quercus upload format, bonus marks.

## 13. Starting the build (new chat)
- Server: Flask, **same structure and style as the Beamer+ server**. Must run locally with `python app.py`; the web address (lectern.changapp.net) gets set up later.
- Ask questions at any point rather than guessing.
- Upload at the start of the new chat:
  1. This plan (`lectern-plan.md`).
  2. Beamer+'s `app.py`, its folder layout, and `requirements.txt` (if any), so Lectern's server matches it.
  3. A screenshot of beamer.changapp.net's start page (or connect Claude in Chrome so Claude can open it).
  4. The current tools: `course-page-builder.html`, `grade-builder.html`, `exam-builder.html`, `suite.css`, `course.cls`, `courses_login.py` (rename references from courses → Lectern), and `grade-builder-plan.md`, `exam-builder-plan.md`.
- First step: the Lectern shell (server, splash, Home, pinned navigation path), then the build order in section 11.

## 14. Accommodation requests (Oct 20 2026)
- Grades → each evaluation: the standard accommodation is its missed-work policy (makeups / weight moved; written out as `accom.standard` on save, for the form and emails; none when it counts as zero or is in a group), "students must request it", "students can request an alternate accommodation", request-by date and time with the evaluations' calendar (deadline in `LECTERN_TIMEZONE`, default America/Toronto).
- Course page: Request Accommodation button (week card and marking scheme) when either request is on; after the deadline, "The deadline for accommodation requests has passed" (the page's script, and the form itself).
- The button opens Lectern's own form (`/request`), so it works in Canvas too. Endpoints: `GET /api/accommodations/evaluation`, `POST …/verify`, `POST …/submit` (CORS open), `POST …/decide` (instructor's GitHub token).
- Students are matched on email + identifier + first + last name, all against the gradebook (Email field required; dropped students excluded). Rate-limited per address.
- Requests: `<course>/<term>/accommodations.json` in the private repo, written by the GitHub App (private key on the server). Decisions are committed with the instructor's own token.
- Email over SMTP: a receipt on submit; the decision (with an optional note) on approve/reject.
- Lectern: Accommodations part on the offering page (waiting count) and its own page `#/<course>/<term>/accommodations`: Waiting / Decided / All, filter by evaluation, Approve / Reject, change a decision.
- Folder mode: the page shows the folder's copy; deciding needs GitHub sign-in.

## 15. Course hub (Oct 24 2026)
- Lectern serves the course page in tabs at `/c/<handle>/<course>/<term>/` (server/hub.py, static/js/hub.js); `/p/…/info.html` redirects there once `course.json` exists.
- The builder writes `course.json` beside `info.html`, and opens a page from `course.json` when there is one.
- Tabs: Overview, This week (opens here), Lectures, Evaluations, Announcements, Policies, My accommodations. Each is public or signed-in only (the builder's "Course hub tabs"); My accommodations always signed-in. The API leaves out what a viewer may not see.
- New builder section: Meeting Times & Office Hours (structured weekly times) for This week's day-by-day list.
- Evaluations come from the gradebook's scheme only (no hand-made Grading table fallback).
- Next pieces: student/TA magic-link sign-in, accommodations in the hub, grades, discussions, notifications, end of term.
- Oct 24 (later): the builder's editor is the hub itself (same header, tabs and drawing, hub-view.js) with editing hooks; announcements are written on the Announcements tab; info.html / Copy HTML for Quercus are gone (course.json is the page; older info.html pages open and save as course.json).
