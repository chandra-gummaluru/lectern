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
