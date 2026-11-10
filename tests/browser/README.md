# Browser walkthroughs

Each `flow_*.py` drives Lectern in Chromium (Playwright) against the real server, running in this
process with an empty data folder of its own. Run one at a time:

    pip install -r requirements-dev.txt
    python -m playwright install chromium
    python tests/browser/flow_auth.py

Screenshots go in `shots/` (not committed). Most flows assert as they go and print what they saw;
a flow is fine when it ends without an error (several print `<name>: OK`).

## Helpers

- `harness.py`: the server (`Server`), an account, putting files in it, signing a page in.
- `walkthrough.py`: for the flows first written against a fake GitHub. They still describe an account's
  files as two repositories (`Walkthrough`, `Repo`, `make_walkthrough()`), and this maps them onto the
  real server. One server per process.
- `fakegithub.py`: a small in-memory GitHub API, for the builders opened on their own (`/tools/…`), which
  still talk to GitHub (`flow_standalone.py`).

## The flows

| Area | Flows |
|---|---|
| Accounts and the shell | `flow_auth`, `flow_shell`, `flow_bar`, `flow_nav`, `flow_save`, `flow_install` |
| Teaching teams and roles | `flow_teams`, `flow_team`, `flow_roles` |
| Gradebook | `flow_evals`, `flow_fx`, `flow_cellst`, `flow_finals`, `flow_makeups`, `flow_policies` |
| Exams | `flow_examui`, `flow_standalone` |
| Course page | `flow_hub`, `flow_course`, `flow_drag`, `flow_lectures`, `flow_parts`, `flow_sections`, `flow_links`, `flow_evalfiles`, `flow_ann` |
| Students | `flow_students`, `flow_accommodations`, `flow_attendance`, `flow_mail` |
