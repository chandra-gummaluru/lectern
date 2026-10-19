# Exam Builder: Plan

October 15, 2026

## Overview

The Exam Builder is a single HTML tool, like the Course Page Builder, for writing exams as structured questions while keeping every question body and solution in LaTeX. It handles structure, numbering, points, versions and layout, and generates `.tex` files that use my existing exam template. Nothing is built yet; this is the plan.

Decisions so far:

| Decision | Choice |
| --- | --- |
| LaTeX output | Match my existing exam template (I share a current exam's `.tex` plus any `.cls`/`.sty`) |
| Preview | Undecided (see Preview) |
| Storage | A private GitHub repo, same Open/Save workflow as the Course Page Builder |
| Version 1 extras | Per-question variants, points summary, answer-space control, cover page, rubric comments |
| Later | Question bank, real PDF preview, importing an existing `.tex` exam |

## Storage

Each exam lives in a private repo (not `courses-utor`, which is public) as one project file that the tool edits, plus `.tex` files it regenerates on every save.

```
exams-utor/                      (private repo; name to be confirmed)
  csc258/f26/midterm/
    exam.json                    the source of truth the tool edits
    course.cls                   written by the tool on every save (its built-in copy)
    midterm.tex                  generated: student copy (midterm-A.tex, midterm-B.tex, … with versions)
    midterm-key.tex              generated: answer key (\input of the student copy with [solutions])
    midterm-guide.tex            generated: marking guide (\input with [marking])
    figures/                     images the questions use
```

- Folders follow the course pages (course, then term), with one more level for the exam (midterm, final, quiz2).
- The generated `.tex` files are never edited by hand; changes go through the tool.
- The GitHub connection, token handling and Open/Save window work as in the Course Page Builder, pointed at this repo.

## The editor

The editor is a list of question cards, each opening a question editor window like the course builder's announcement editor.

**Exam settings:** course, term, exam name, date, duration, instructions, cover page on or off, target total points, number of versions.

**Question list:** reorderable cards showing number, type, points and a rendered preview; clicking a card opens its editor.

**Question editor fields (every type):**

- Type, points, and space after (none, a set height, fill the rest of the page, or new page before)
- Body: a LaTeX editor with a live maths preview beside it
- Solution: LaTeX, shown only in the answer key
- Tags (topic, difficulty, lecture) and private notes, never printed

**Fields by type:**

| Type | Extra fields |
| --- | --- |
| Multiple choice | One option per row; mark the correct one(s); shuffle choices on/off; keep the last option fixed (e.g. "None of the above") |
| True/false | The answer |
| Short answer | Answer space |
| Fill in the box | Box size |
| Long answer / proof | Answer space |
| Multi-part | Sub-parts (a), (b), (c), each with its own body, points, space and solution |

**Points summary panel:** totals per question, per tag and per type, with a warning when the total doesn't match the target.

## Generating the LaTeX

My existing template drives the output: the tool fills in snippets taken from it and never changes the LaTeX I write inside a question.

- **Template snippets:** from a current exam I share, Claude extracts the preamble, cover page, how a question starts, how points are printed, multiple-choice options, answer space, and how solutions are switched on. The tool fills these in.
- **Solutions:** the answer key is the same document with my template's solutions switch turned on, not a separate copy, so the two can't drift apart.
- **Versions:** a seed per version shuffles question order (some questions can be pinned in place, e.g. always first) and choice order. Each version gets its own key and a table mapping its question numbers back to version A's, for marking.

## Preview

The preview shows text and maths instantly with a built-in maths renderer (KaTeX); I compile the real PDF myself.

- My common macros go into the tool's settings so the preview understands them.
- Anything it can't render (TikZ, custom environments) appears as a labelled grey box, e.g. "TikZ figure", so the preview never pretends to be the PDF.


## Decisions from the Oct 15 discussion

**Versions: per-question variants, no shuffling.** Each question card has variant tabs (A, B, …). Version B of the exam uses variant B of every question; a question with one variant is shared by all versions. Question order is the same in every version. Seeds, pinning, choice shuffling and version mapping tables are dropped. Check: warn when a question's variants have different points.

**Cover page.** Field list, each field with a label, type and size: text line (set length), digit boxes (set number of digits, e.g. student number). A free LaTeX block under the fields for instructions or other information. Bubble-style ID entry may be needed if scanned (Crowdmark).

**Page settings (exam-wide).** Blank top margin on every page with a settable height (room for scanner QR codes); page numbers on by default with an off switch. Check that scanner stamps don't overlap page numbers.

**Page items in the question list** (draggable between questions, never count toward points): page break · rough-work page ("Rough work — not marked") · content page with its own LaTeX body (formula sheet, extra instructions).

**Rubric (Crowdmark-style comment library).** Each question (and part) has a list of ready-made comments, each a short note plus a point change (+ or −). Each question is set to **Start at zero** or **Start at full**; comments of either sign are allowed in both. Checks: positive comments can reach full marks; score stays between 0 and the question's points. A "Correct" / "Fully correct" comment covers perfect answers. Crowdmark can import comment libraries (per Chandra). Open: one rubric per variant or shared.

**Three outputs from one source:** student exam (questions + answer space) · answer key (+ solutions) · marking guide (+ solutions + rubric comments, with each question's start-at-zero/full setting by its points). Implemented as two switches in the generated LaTeX.

**Figures.** TikZ stays in the question body. Image files: an image button in the question editor picks from the exam's `figures/` folder or uploads one (waiting upload committed with the next save, as in the Course Page Builder); the tool inserts the `\includegraphics` line.

**Preview: undecided.** Options considered:
- KaTeX: instant, maths only, no layout/TikZ/custom packages. Useful while typing either way.
- Local LaTeX: needs a background helper on each machine (a web page can't run programs). Not preferred.
- GitHub Actions compile on a "Compile" button: real PDF from any computer, ~1 min each; private repos get ~2,000 free minutes/month (~66/day, ~30–60 compiles).
- Overleaf GitHub sync: works with private repos (paid feature Chandra already has); manual "Pull from GitHub" then recompile; no Action minutes.
- In-browser engine (SwiftLaTeX/WASM): free, a few seconds after first load; may lack packages, no shell-escape (`minted`), no system fonts, slow heavy TikZ. Test against Chandra's template before deciding.
Concern: exams are layout-heavy, so frequent compiles are likely; a 1-minute round trip may be too slow.

**Security.** The private repo holds exams: "Remember on this computer" off by default.

**Still open.** Preview approach · accommodations (e.g. large-print output) · scope of version 1 (suggested start: multiple choice, short answer, multi-part) · shared vs per-variant rubrics.

## Status (Oct 15 2026): first build

`exam-builder.html` (single file, opened locally) has the editor, per-question variants, cover page fields (text line, digit boxes, digit bubbles), page items, rubric comments with start at zero/full, points panel and checks, KaTeX preview (student copy, answer key, marking guide per version), figure picker/uploads, and the GitHub Open/Save window (course, term, exam). Tested in a browser against a mocked GitHub API; the generated LaTeX compiles with pdflatex.

- Save writes one commit: `exam.json`, `course.cls` (built into the tool), `<exam>[-A].tex` plus `-key.tex` and `-guide.tex` wrappers per version, waiting figure uploads, figures copied from the exam it started from, and removes generated `.tex` files no longer made.
- "Remember on this computer" is off by default; connecting warns if the repo is public. Folders starting with `_` (e.g. `_template`) are skipped.
- The LaTeX uses Chandra's `course` class, tidied as `course.cls` v2.1 (Oct 15): `solutions` / `marking` class options (the -key and -guide wrappers pass them), `solution` built on the comment package (v2.0 printed the solution text in the student copy), `marking` environment with `\rubric{±n}{text}`, redefinable `\StudentInfo` (`\InfoBoxRow`, `\InfoBoxRowPair`, `\InfoLineRow`, `\DigitBubbles`), `\answerspace`, `\answerbox`, `\correctchoice`, `\TrueFalse`, `\RoughWorkPage`, `\EndOfExam`, `\SetScanMargin`, `\showpagenumbers`, `\ExamDate`, `\Version`. The tool carries its own copy of the class and Save writes it into every exam folder (no `_template/` needed); change the class by updating the tool.
- One screen, no pop-up editors (Oct 15): the exam on a white sheet laid out like the student copy (cover, header, questions, page breaks), updating as you type; clicking a block edits it in a sidebar docked to the right edge (soft-filled fields, no example text, row buttons on hover) (question, answers, marks and solution up front; marking, layout, tags and variants folded into one-line summaries). With nothing selected the panel shows points and checks. Cover labels and instructions are plain text (one instruction per line). A switch above the sheet shows the student copy, answer key or marking guide; the separate Preview mode is gone. On small screens the panel slides up from the bottom.
- Points are whole numbers (the class counts with LaTeX counters); the checks flag part marks.
- Not built yet: real PDF compile (preview decision open), Crowdmark rubric export, accommodations output.

## Question model (Oct 16 2026, exam.json format exam-builder/2)

- Questions are built from pieces instead of fixed types. Each question (and each variant of it) is a node: answer type (written, multiple choice, multiple select, true or false), text, marks, solution, rubric, space after, and its own sub-questions. Sub-questions are nodes too, two levels deep: (a), (b) and (i), (ii). A node with sub-questions takes its marks from them. Marking mode (start at zero/full) is set once per question.
- Multiple choice is one type with a "Multiple answers" switch on its toolbar (stored as type ms): off, one correct option and round bubbles; on, any number correct and square checkboxes (ticked in the key). Layout: stacked, in a row, 2 or 3 columns. There is no separate fill-in-the-blanks type: blanks and boxes go into any question's text.
- Question text wraps back to the left margin after its first line, as in print.
- Answer components sit inside the text as [[id]], drawn as chips in the editor: blank line, box, number box, fraction, row of cells. Each holds its answer for the key. "Fill in the blanks" is a written question with no space and components in the text.
- Editing on the page (Oct 16): no side panel. Everything is typed on the sheet: cover text, header, question text (rich text: formatting as itself, maths and answer pieces as chips that look like the printed boxes), options (click a bubble or box to mark the answer), marks in the points box, answer space by dragging its bottom edge. Add question inserts a written question straight away (cursor in its text). Nothing floats over the page: an edit bar under the top bar shows the tools for whatever is selected. Question or part: answer type (e.g. "Written ▾"), layout menu for multiple choice (with Multiple answers), formatting, maths, LaTeX, Insert ▾ (answer pieces, TikZ figure, image), + Sub-question, New page, own variant / remove variant (with versions); on a part, move up/down and Delete part. Cover: + Student field, Points table (with a Score row option for the blank marks row), Instructions (on/off; the text is kept), "Good luck!", Remove cover. Student field (click its boxes; outlined on the page): number of boxes, beside the one above, move, remove. Student fields are character boxes only (older bubble and line fields become boxes). Nothing selected: a hint. Each control lives in one place only (start at full/zero in the marking guide, deleting questions with the bin, answer space set on the space itself). Tags and a private note sit in a strip under each question (never printed) (shown when it's selected or hovered, faintly when it has any; hidden in the marking guide): tag chips with ×, an "Add a tag" box (Enter or comma adds, Backspace removes the last), and a one-line private note. Answer space settings are on the edit bar once a question has space (− height + in half-centimetre steps, Rest of page, ×; a rest-of-page space offers Set a height); on the page the space can be dragged taller or shorter from its bottom edge, and a question with none shows a faint "+ Answer space" link. Switching the sheet to Answer key or Marking guide makes solutions and rubric comments editable in place. Maths is edited in place: clicking a maths chip (or Σ) turns it into its $…$ source in the line, no box or preview; it renders again on Enter, Esc or clicking away, and a toggle puts it on its own line. Code blocks (toolbar </> button, replacing the raw-LaTeX button) are lstlistings edited on the page with a Python / Plain style switch (the class's python and struct styles; other listing options are kept); the code is saved verbatim. TikZ figures (Insert menu) are blocks on the page with their code editable in place and a Centred toggle; drawn only in the PDF. The top bar holds the view switch (Student copy, Marking guide: in the marking guide only solutions and rubric (and the answer itself: the right option, true/false, answer-box answers) are editable, everything else is read-only with add/move/delete hidden; the .tex files still include the answer key) and a version dropdown (only with more than one version) on the left, zoom on the right; there is no LaTeX button (Save writes the .tex files). Points boxes are one text line tall. The page's side margins are 1 inch, as in the class, so the page's text width (16.51cm) and line breaks match the PDF. Settings is a third page in the view switch (Student copy · Marking guide · Settings), replacing the Exam settings button: versions (1–6), target total, blank space at the top, page numbers, LaTeX macros and extra preamble, all applied as you type. Title, course, term, instructors, date and duration stay on the cover. View switch (Student copy · Solutions · Marking guide) and version tabs on the left of the top bar; zoom and Exam settings on the right, before LaTeX and Save. Zoom control (− / percentage, click for 100% / + / Fit, 50–250%, remembered): CSS zoom on the sheet; toolbar, block controls and badges are counter-zoomed so they stay their normal size. Checks and points live in a dock along the bottom, like a console: a thin bar (problem count, marks per version against the target, question count) that opens into the list of problems; click one to jump to it. Open/closed is remembered (localStorage exam-builder.dock).
- Older exams (exam-builder/1) are upgraded when opened: multi-part becomes sub-questions, fill-in-the-box becomes a box component.
- course.cls v2.5: two fields side by side are one box apart, so their boxes line up with the rows above and below; the shared box size is the text width divided by the widest row (at least 16; a pair counts its boxes plus one). v2.4: every student box is one size, \\StudentBoxSize (default a sixteenth of the text width; rows with more boxes than fit shrink). The tool sets it from the widest row on the cover (at least 16 boxes, or a side-by-side pair with its gap) so every row matches, on the page and in the PDF. An exam with no questions leaves out the points table and the empty question list so it still compiles. v2.3 added \\showscorerowfalse (points table without the blank Score row). v2.2 added subparts / \subpart[n], \partpoints{n}, \correctcheckbox, the choicecols environment, and \ansblank, \ansbox, \ansnum, \ansfrac, \anscells (answers shown only with solutions).

## Start screen (Oct 16 2026)
Same design as the Course Page Builder's (warm paper background, "EXAM BUILDER" kicker, serif "Your exams", lede). The GitHub connection sits in the source box (connect form inline; Remember off by default; warns if the repo is public). "Continue editing" bar when an exam is open. "EXAMS" grid: one card per exam.json, newest term first: strip course/term/exam plus the exam date, serif title, course code and term, chips (questions, marks, versions), footer "Saved <date of last commit>" and duration. Dashed "New exam" card opens the New exam window (blank or a copy). "Open a file" link for an exam.json on this computer; dropping a file still works. The toolbar's Home icon replaces Open.

## Later (not in version 1)

- Question bank: reuse questions across exams and terms, searchable by tag
- Real PDF preview in the browser
- Importing an existing `.tex` exam into the tool

## Before building

These are the inputs and answers needed before the build starts.

- [ ] Share one or two recent exams (`.tex` and compiled PDF) covering every question type I use
- [ ] Share any `.cls`/`.sty` files they load that are my own
- [ ] Create the private repo on GitHub and confirm its name (suggested: `exams-utor`)

## Context for a new chat

The Exam Builder should reuse the Course Page Builder's patterns and look, described in the project note `claude/course-page-links.md`.

- **One HTML file** opened locally in the browser (not a claude.ai artifact, which can't reach GitHub).
- **GitHub access** with a fine-grained personal access token (Contents: Read and write), kept in the browser's storage, never in the file; saving makes one commit through the git data API.
- **One Open/Save window:** the GitHub connection on top, then course and term dropdowns with "New course…" / "New term…" last, plus an exam dropdown for this tool.
- **Look:** Edit/Preview toggle, amber notices with an icon for warnings, styled dropdowns and checkboxes, and editor windows that don't close on a stray click or Escape.
- **Lessons from that build:** a literal backtick in markup or `</script>` inside a template string breaks the tool's script; test every change in a browser against a mocked GitHub API.

## The suite (shared with the Course Page Builder and the Exam/Grade Builder)

All three tools carry the same **Suite** style block, last in their styles so it has the final say (the master copy is suite.css). It sets:
- Sizes: controls 36px with 7px corners; compact controls inside a page 30px; dropdowns in windows 42px. Cards 10px corners, menus and windows 12px. Text 14px, small 13px; EB Garamond for page headings and card titles; the mono font for paths and short names.
- Elements: outlined buttons and dark main buttons; trash-can deletes (red on hover; × only for removing a chip); dashed gold "Add …" buttons; text and number fields; dropdowns with the same chevron; checkboxes as rounded boxes filled with ink; switches ink when on; one menu pop-up; amber notices and warning pills; the drawn arrow.
- Layers: bars < windows < menus < messages.
- The top bar: Home · tabs · status (the path in grey mono, then the amber pill when not saved), then the tool's own buttons, with the dark Save on the far right.
- The Save window when not connected: an amber notice to connect on the start screen, "Download a copy instead…" and Cancel.
- Settings pages: the warm page, a 40px serif "Settings" heading, one white card per section with a 22px serif title.
- Pages you click into show their path at the top (earlier steps are links). Moving between pages, by the path, the tabs or clicking into something, remembers how far down each page was and returns there; a page not visited yet opens at its top.
Any new element uses these; a change to the shared look goes into suite.css and then into all three.
