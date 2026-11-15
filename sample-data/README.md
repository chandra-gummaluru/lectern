# Sample data

Made-up data for trying Lectern and for its tests. Nothing here is real.

- `class-list.csv`: 40 students, laid out like a Quercus gradebook export. On an offering's page in Lectern: Students → import a class list.
- `demo-courses/` (public files: course pages) and `demo-courses-private/` (private files: gradebooks with students and marks, and a few exams): 11 course offerings (CSC108, CSC148, CSC209, CSC258, f25 to w27), laid out as an account's files are on the server (`data/files/<account id>/pub` and `…/priv`). The browser walkthroughs (tests/browser/) load them from here.
- `demo-course/`: a generic made-up course (DEMO101, A Sample Course) with 30 students, marks and a midterm. Lectern's **Load the demo course** (Home) loads it as `demo101`, dated to the current term.
