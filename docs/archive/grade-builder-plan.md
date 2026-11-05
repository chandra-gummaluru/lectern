# Grade Builder

A single HTML file, like the Course Page Builder and the Exam Builder, for keeping each course's grades. It opens in a browser and saves to a **private** GitHub repository (e.g. `owner/grades`) through the GitHub API, with the same start screen, connection and Open/Save window as the other builders.

## Repository layout

```
grades/                    (private repo)
  csc258/f26/grades.json   one gradebook per course and term
  csc108/f26/grades.json
```

Each save is one commit, so the repository's history is a record of every change to the marks.

## What a gradebook holds (`grades.json`, format `grade-builder/1`)

- **Evaluations**: name, a short name (required and unique: mark files use it as the column heading; new evaluations get E1, E2…, older gradebooks get one made from the name), total points, default weight (%), and what happens if a student doesn't submit. Marks arrive already final from Crowdmark, MarkUs and so on, so there are no late penalties here.
  - Makeups: each evaluation can have one or more makeups (each with its own name and total points, and its own column in the grid). A student who didn't submit the original but has a mark in one of its makeups gets that mark instead. A makeup never counts by itself; moving or deleting an evaluation moves or deletes its makeups too.
  - If not submitted (and no makeup mark): zero · its weight moves: tick the evaluations that receive it and give each a share (% of its weight; a newly ticked one starts at what's left); whatever isn't moved stays on the evaluation and counts as zero (a partial penalty), shown as a last row with the evaluation's own name; shares over 100% are flagged. Each row shows the receiving evaluation's weight now → after. Older "by weight" / "equally" splits are converted to the same shares on open, so grades don't change. Older gradebooks that chose a makeup as the policy are converted on open.
- **Groups** ("assignment groups"): a name, a weight, and "the best N of" its member evaluations. For each student the best N members count, each worth the group's weight ÷ N; the rest aren't counted. Members don't use their own weight or reweight policy (not submitted counts as zero, so it's usually not counted), can't receive reweighted weight, and have no per-student changes; makeups still work for them.
- **Students**, keyed by student number (with name, UTORid, email and section), each Enrolled or Dropped. A dropped student keeps their marks but is left out of the class average, histogram, marked count and checks; the grid hides them unless "Show dropped" is ticked; exports have a Status column.
- **Marks**, always points out of the evaluation's total, or a status: Not submitted (⊘; follows the evaluation's policy: zero, shift its weight, or a makeup), Academic integrity violation (shield; always zero, never shifted or made up), Excused (dashed circle; doesn't count, the student's other evaluations scale; in a group it's left out), Deferred (clock; still to come). In a cell or a file: m, aiv, excused (ex), deferred (def).
- **Accommodations** (overrides) for one student and one evaluation: their own weight (their other evaluations scale so the total stays 100%; 0 excuses it) and their own policy if not submitted (zero, or the weight moves, with the full redistribution: targets, by weight / equally / custom, what stays). Set from the student's page (Accommodations → Change) or from a mark's edit bar (Accommodation).
- **Group accommodations** for one student (a group's members follow the group, so the accommodation is on the group): a new weight for the whole group (others scale; 0% excuses the group), how many count ("their best N"), and excused members (they don't count at all; the best N come from the rest). On the student's page the group has its own row with Change, and its members show underneath with their results and whether they count, aren't counted or are excused; a member's Accommodation in the grid opens the group's.

## Student fields (Settings → Students)

- **The identifier**: required and unique; how students are organised and matched in class lists and mark files. Its name is set in Settings ("Student Identifier" by default; e.g. UTORid or Student number) and shown wherever the tool refers to it.
- **First Name** and **Last Name** (shown as "Last, First").
- **Custom fields**: any others (Student #, Email, Section, Phone…), added, renamed or deleted in Settings. Only a field called **Section** filters: its values become the section chips on Students and Grades, the sections in the Statistics dropdown, and By Section.
- Marks files can identify students by the identifier or any custom field (e.g. a UTORid). The class-list import maps a column to the identifier, first and last name (or one "Last, First" column), and each custom field. Exports carry the identifier, names and custom fields.
- Older gradebooks convert on open: the identifier is named "Student number", names are split into first and last, and UTORid / email / section become custom fields.

## Course-wide policies (the Settings tab)

Applied to the course grade, in this order:
1. **Ranges**: grades from X to Y become Z (e.g. 48–49.99 → 50); overlapping ranges are flagged (the first one wins).
2. **Rounding**: to 1, 5 or 10 (or not at all), to the nearest, always up or always down, with a live example.
3. **Automatic fail**: if an evaluation (or a group: the average of the members that count) is below X%, the course grade is capped at, or set to, Y%. Not submitted counts as 0 unless a makeup counts; excused, deferred or unmarked work doesn't trigger it.

The Grade column shows the adjusted grade (dotted underline; hover for the calculated grade and each rule applied; a red flag marks an automatic fail). Statistics, averages and the final-grades export use it; the export also has the grade before the rules and the rules applied.

## How a grade is worked out

1. Each mark becomes a fraction of its total.
2. Work not submitted takes a makeup's mark if the student has one; otherwise it follows its policy (the student's override first): zero, or its weight moves to the chosen evaluations. A target that was itself missed and reweights passes the weight on.
3. In each group, the best N members that are marked share the group's weight equally; the others aren't counted. Until every member is in, the grade so far uses the best of those marked.
4. If a student's weights were changed, their weights are scaled back to the course total.
5. "So far" averages what's been marked; the final grade appears once every evaluation is settled.

## Screens

The top bar's tabs are Evaluations · Students · Statistics · Grades · Settings. A page you click into shows its path at the top (Students › Castillo, Maya › Midterm; Evaluations › Assignment 2; Grades › Castillo, Maya when opened from the grid); each earlier step is a link back.

Each evaluation has its own colour (a makeup shares its original's); colours mean evaluations only, so every student's avatar is the same soft yellow. used in the grid headers, the weight bars, the evaluation cards and the override chips. Grades are banded: red under 50%, gold under 70%, green above.


- **Start screen**: gradebooks as cards (course and term, the class average, a large faint line icon on the right as in the Course Page Builder (one per course, the same in every term, never repeated on screen), last saved), New gradebook, Open a file.
- **Grades**: on the warm page, a serif heading, Upload marks and the legend; search, section chips and Show dropped; then the grid in a white card. Sort by clicking a column header (Student, any evaluation, or Grade; again to reverse; an arrow marks the sorted column; marks and grades start highest first; unmarked last). Headers show the evaluation's colour dot, short name and points (makeups just "/50"). A sticky Student column (name with the number under it) and a Grade column (just the percentage; red under 50%). Type points or a status word (m, aiv, ex, def); a status shows its icon; Backspace or a mark clears it; Enter moves down. A makeup cell is struck through and locked for a student who has the regular mark. The edit bar has a Status dropdown (with the status's icon) and Accommodation.
- **Evaluations**: a heading with Add a group and Add an evaluation on the right (like Students), the weight bar, then a list of long cards in the Course Page Builder's style: each evaluation's colour dot, short name and serif title, a sentence saying what it's out of and what happens if it isn't submitted, and its makeups on the left; Upload marks and Edit on the right. A group is a long card with its rule ("The best 5 of 7 count, 10% each") and squares, with its members as smaller sub-cards inside it. Cards are reordered by dragging (the whole card is the handle, with a grab hand on hover; while dragging, the card becomes an empty dashed slot that moves through the list as the other cards slide out of its way; cancelling puts everything back): a lone evaluation or a whole group in the list, or a member inside its group. The order is the course's: grid columns, the weight bar and exports follow it. Edit opens the evaluation's page (with its path at the top): name, short name, points, weight; makeups (add, rename, remove); "If a student doesn't submit it" as two tiles (Counts as zero / Shift its weight); for a move, a list of the other evaluations to tick, each with its share and its weight now → after; and Delete. A group's page has the name, weight, "Each student's best − N +" stepper, squares, and its members as a ticked list.
- **Students**: heading with "N enrolled · N dropped · N with accommodations", a With accommodations filter, Import a class list and Add a student (a form: number, name, UTORid, email, section); search, section chips, Show dropped; the list (avatar, name, number and UTORid, the section and Enrolled/Dropped as plain text, a gold Accommodation badge for anyone with one (hover for which evaluations), and a Drop / Re-enrol button), no grades. Clicking a student (or their name on the Grades page, or Accommodation on a mark) opens their page in the Students tab, with its path at the top. It shows their details (read-only: they come from the class list), their accommodations (every evaluation with the policy that applies to them and, to the left of its button, their result in large type: the percentage coloured by band with the mark under it, a makeup's result when it counts instead, Not submitted, or — if not marked yet; Change / Edit opens the accommodation on the same page), Notes (why anything was done; saved with the gradebook, not exported; a note icon in the list shows them on hover), and delete. Dropping is the Drop button on their row.
- **Statistics**: "Show [● Course grade or an evaluation ▾] for [All students / a section / Selected students… / One student… ▾]" at the top. Both are the tool's own dropdowns (a button that opens a list in the usual pop-up style): the first shows each evaluation's coloured circle, name and short name, with Course grade first and the current one ticked; the second lists the filter field's values under its name. Picking students brings up a search. Then one summary card (the average large, with the whole class beside it for a subset; median, range, under 50%, and not submitted for an evaluation), the **Distribution** histogram (labelled axes, the average marked, centred; before anything is marked, the same empty frame with "Nothing marked yet"), and for the course grade **By Evaluation**: one row per evaluation on a shared 0–100% scale (a line from the lowest to the highest mark, a band over the middle half, a dot for the average, a tick for the median; the whole class's average as a faint diamond for a subset) with the average, median and how many didn't submit on the right. With a filter field, **By Section** (named after the field) in the same style. One student: their grade, standing, their place on the class histogram, and their marks beside the class average.
- **Uploading marks**: a CSV (commas, tabs or spaces) whose first column is the student (UTORid, student number or email) and whose other columns are headed by short names, e.g. `studentid,MT,FT` / `gummalur,24,32`; `m` means not submitted, blanks are skipped. **Upload marks** on an evaluation's card takes just its column; **Upload marks** on the Grades page (or Import → Marks) takes every matching column. The window lets you choose the columns: on an evaluation, the Student ID column and the Points column; on the Grades page, the Student ID column and, for every other column, which evaluation it fills (or Ignore). It guesses them: the ID column is the one matching the most students; a points column is the one headed with the short name, else Total / Score / Points / Mark / Grade, else the first numeric one. A live summary shows, per evaluation, how many marks, how many replace existing ones, any above the total or not numbers, columns that aren't short names, and IDs not in the class list; nothing changes until you confirm (and it can be undone).
- **Import**: class list (anyone on it is enrolled again; it offers to mark enrolled students missing from it as dropped).
- **Export**: final grades CSV; all marks CSV in the upload format (studentid, a column per short name, then name, UTORid, status and grade), so it can be edited and uploaded back.
- A bottom bar shows problems (weights not 100%, marks above the total, policies pointing nowhere, duplicate student numbers), number of students, how much is marked, and the class average so far.

## Conventions

Use the same UI elements everywhere. Menus (Import, Export, the Statistics dropdowns) all use one pop-up: fixed to the screen under their button (or above it if there's no room), lined up with its edge, items sized to their text; clicking the button again, Esc, clicking elsewhere, scrolling the page or resizing closes it. Any arrow from one value to another is the drawn arrow icon (ARROW(): a rounded line arrow, grey, or tinted with the evaluation's colour), never a text "→". Every delete is a trash-can icon button (with a tooltip naming what it deletes, red on hover), and every delete can be undone. Short warnings are the amber warning pill with a ⚠ icon (as in "Unsaved"); longer warnings are the amber notice panel; anything flagged in place (an over-total or non-number mark in the grid, weights over 100% on the bar, custom shares over 100%, a missing or duplicate short name) uses the same amber tint and ⚠. Red is kept for meaning, not warnings: low grades, zeros, and delete buttons.

## Not yet

Letter grades and grade scales (beyond ranges); sections as filters; a Quercus-ready grade upload file; bonus/extra-credit evaluations.

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
