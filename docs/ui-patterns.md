# UI patterns

Named patterns for Lectern and the course page (hub). When a request says "use the X style", it means one of these.

## Item Head

The head of a page for one thing: a request, an announcement, a section, an evaluation, a discussion post.
The reference is the accommodation/remark request page in Lectern (`accomPage` → `drawOne`, static/js/lectern.js).

```
[icon] ALTERNATE ACCOMMODATION                       (Status pill, optional, right)
Student, Test / Test 1
1234567890 · chandra.gummaluru@mail.utoronto.ca · Asked Oct 26, 2026, 12:14
─────────────────────────────────────────────
SECTION HEADING
```

1. **Kicker:** a small icon (15px, `--home-ink-3`) beside the gray caps kicker (700 11px, `.08em` letter-spacing, uppercase). The kicker names the type of thing, e.g. ALTERNATE ACCOMMODATION, REMARK REQUEST, ANNOUNCEMENT or DISCUSSION POST.
2. **Title:** serif, 30px, flush left under the kicker's icon, set tight (`line-height` 1.1, about 1px gap).
   - Main part: dark. For a person it reads "Last, First".
   - " / " and the second part: `--home-ink-3`. The second part is what the item is about, such as the evaluation or activity.
   - Each part is a link with no underline until hover. The name opens the student and the second part opens the evaluation.
3. **Meta line:** one gray line of facts joined by " · ", like the student card in the gradebook, e.g. number · email · "Asked <time>". Links in it have no underline until hover. Use no grids of labelled facts.
4. **Status:** an outlined pill on the right of the kicker and title, spanning both rows (green for approved, red for rejected, amber for pending). Use no big status icon.
5. **Rule:** then a rule, and the sections, each with a gray caps heading.

Markup: `.lx-ed-head` > `.lx-kicon.big` + `.gr-tt` (`.gr-kind`, `h2`) [+ `.lt-req-pill`], then `p.lt-req-meta`. The CSS is in static/css/shell.css: `.lx-ed-head:has(> .gr-tt > .gr-kind)`, `.lt-req-of`, `.lt-req-meta` and `.lt-req-who`.

For an evaluation, the title is its name, then its own title in gray: "Test 1 / Midterm Test". The kicker is just the type (REMARK REQUEST), with no evaluation in it.

This is only for item pages. List previews (cards in a list) keep their own look.

## Comment Thread

Decisions and replies on a request look like discussion comments:

- an avatar circle (30px) with the person's initials;
- the name, then the time, in gray;
- the text under the name, with no bubble;
- the teaching team's avatar and name in yellow (`#fbf0d2` / `#e8cf7c` / `#9a7400`);
- a Reply button (reply icon + "Reply", gray, no border) under the thread, which opens a rich text box in place.

On requests, the box also has an Approve / Reject switch.

## Emails

Every email Lectern sends looks and reads the same way. The layout is in server/mailer.py (`page`, `to_html`). Emails are written once, as plain text, and the HTML version is made from that text.

**Layout:** a white card on the splash's sage paper.

- **Header:** the course's name in the serif ("CSC258: Computer Organization"), then its term and school in grey small capitals. An account's emails say "Lectern", with the school under it.
- **Title:** the subject, without the course code (that's in the header).
- **Footer:** "Sent with Lectern for CSC258 Winter 2027 at University of Toronto." No "replies go to" line: emails will come from a no-reply address.

**Wording:**

1. **Subject:** "<who>: <what>", in sentence case. *Who* is "Lectern" for an account's emails, or the course code for a course's ("CSC258: your mark for Test 1 is out"). A code goes first ("12345678 is your code for CSC258"), so phones can offer it.
2. **Greeting:** `mailer.hi(name)` gives "Hi Maya," or, without a name, "Hi,". There's no sign-off, because the header says who it's from. A course's own signature is added only to its emails.
3. **The course in the text:** its code (CSC258). The header already has its full name and term.
4. **One action:** a sentence ending in ":", then the link on a line of its own. It becomes a button labelled by where it goes (`BUTTONS`), with the link under it to copy. How long the link works goes in that sentence ("open this link within an hour:").
5. **A code:** on its own line, indented. It shows centred in a gold box, and one click selects all of it.
6. **What someone wrote** (a request, the instructor's note): indented four spaces. It shows in a grey quote box.
7. **Not asked for:** end with "If you didn't ask for this, you can ignore this email." (or "If you weren't expecting this, …").
8. **Facts last:** a reference and the like go under a line of just "—". They show small and grey under a rule.
