"""An exam's Print and Scan page (server/scanning.py): its PDFs, uploading scans, marking them, the team's review,
and sending the marks to the gradebook, on the demo course's midterm (which has Marking from scans on).

The scans are made as in test_autograde: the printed PDF's pages, written on and "scanned". (Skipped without
pdflatex, node, or the scan packages.)
"""
import io
import json
import os
import shutil
import time

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")
pytest.importorskip("pypdfium2")
if not shutil.which("pdflatex"):
    pytest.skip("needs pdflatex", allow_module_level=True)

from server import app, scanning, store  # noqa: E402
from server.autograde import layout  # noqa: E402
from conftest import H, make_user  # noqa: E402
import test_autograde as T  # noqa: E402


@pytest.fixture()
def demo(client, user):
    r = client.post("/api/offerings/demo", headers=H)
    assert r.status_code == 200, r.get_json()
    t = r.get_json()["term"]
    return {"offering": f"demo101/{t}", "exam": "midterm", "t": t}


def q(d, **more):
    return "&".join(f"{k}={v}" for k, v in {**{"offering": d["offering"], "exam": d["exam"]}, **more}.items())


def wait_marked(client, d):
    for _ in range(240):
        j = client.get(f"/api/scans?{q(d)}").get_json()
        if j["job"].get("state") != "running":
            return j
        time.sleep(0.5)
    raise AssertionError("marking didn't finish")


def scans_of(pdf, people, answers):
    """A scanned PDF: one booklet per student, written on."""
    from PIL import Image
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "printed.pdf")
        open(p, "wb").write(pdf)
        t = layout.load_template(p)
        rng = np.random.default_rng(3)
        pages = []
        for k, (who, ans) in enumerate(zip(people, answers)):
            pages += [T.scanned(img, rng) for img in T.booklet(t, who, ans, T.Pen(k), rng)]
        out = io.BytesIO()
        ims = [Image.fromarray(x) for x in pages]
        ims[0].save(out, format="PDF", save_all=True, append_images=ims[1:], resolution=200)
        return out.getvalue(), t


def ids(t, n):
    """The demo midterm's pieces, by question: {label: [ids]} (its ids are random, so found by the exam)."""
    return n


def test_print_scan_mark_review_send(client, user, demo):
    j = client.get(f"/api/scans?{q(demo)}").get_json()
    assert j["exam"]["scan"] and j["exam"]["total"] == 22 and j["copies"][0]["printed"] is None and j["latex"]
    assert j["eval"]["id"] == "mt" and j["can"] == {"print": True, "upload": True, "mark": True}

    for doc in ("key", "guide"):
        r = client.get(f"/api/scans/pdf?{q(demo, doc=doc)}")
        assert r.status_code == 200 and r.data[:4] == b"%PDF"
    r = client.get(f"/api/scans/pdf?{q(demo, doc='student', print=1)}")
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
    pdf = r.data
    j = client.get(f"/api/scans?{q(demo)}").get_json()
    assert j["copies"][0]["printed"]["by"] and not j["copies"][0]["printed"]["changed"]

    # Two students write it: everything right, and a few wrong.
    exam = json.loads(store.Repo(user["id"], "priv").read(f"{demo['offering']}/midterm/exam.json"))
    from server.autograde import grade
    L = {label: n for label, n in grade.leaves(exam, 0)}
    right = lambda n: next(o["id"] for o in n["options"] if o["correct"])
    comp = lambda n, kind: next(k for k, c in n["comps"].items() if c["kind"] == kind)
    good = {f"{L['1']['id']}.{right(L['1'])}": "fill", f"{L['2']['id']}:T": "fill",
            **{f"{L['3']['id']}.{o['id']}": "tick" for o in L["3"]["options"] if o["correct"]},
            f"{L['4']['id']}.{comp(L['4'], 'num')}": "84", f"{L['5']['id']}.{comp(L['5'], 'num')}": "0.375",
            **T.cells(f"{L['6']['id']}.{comp(L['6'], 'cells')}", "1101"),
            f"{L['7']['id']}.{comp(L['7'], 'frac')}:n": "3", f"{L['7']['id']}.{comp(L['7'], 'frac')}:d": "4",
            f"{L['9(a)']['id']}.{right(L['9(a)'])}": "fill", f"{L['9(b)']['id']}:T": "fill", f"{L['9(c)']['id']}.{comp(L['9(c)'], 'num')}": "30",
            f"{L['10']['id']}.{comp(L['10'], 'num')}": "10"}
    wrong = {k: v for k, v in good.items() if not k.startswith(L["1"]["id"]) and not k.startswith(L["2"]["id"])}
    wrong[f"{L['2']['id']}:F"] = "fill"
    wrong[f"{L['10']['id']}.{comp(L['10'], 'num')}"] = "12"
    book = json.loads(store.Repo(user["id"], "priv").read(f"{demo['offering']}/grades.json"))
    people = [s for s in book["students"]][6:8]
    scan, _ = scans_of(pdf, people, [good, wrong])

    # Not before upload; then upload, and a wrong kind of file is refused.
    assert client.post("/api/scans/mark", json={"offering": demo["offering"], "exam": "midterm"}, headers=H).status_code == 409
    bad = client.post(f"/api/scans/upload?{q(demo)}", data={"file": (io.BytesIO(b"hello"), "notes.pdf")}, headers=H, content_type="multipart/form-data")
    assert bad.status_code == 415
    up = client.post(f"/api/scans/upload?{q(demo)}", data={"file": (io.BytesIO(scan), "class scan.pdf")}, headers=H, content_type="multipart/form-data")
    assert up.status_code == 200, up.get_json()
    assert up.get_json()["files"][0]["pages"] == 8 and up.get_json()["files"][0]["name"] == "class scan.pdf"

    # Read as it comes in (the upload starts the marking); Mark, while it's marking, is fine and changes nothing.
    r = client.post("/api/scans/mark", json={"offering": demo["offering"], "exam": "midterm"}, headers=H)
    assert r.status_code == 200, r.get_json()
    j = wait_marked(client, demo)
    assert j["wrote"]["from"] == "class" and j["wrote"]["n"] >= 2, j["wrote"]   # no attendance taken: the class
    assert j["job"]["state"] == "done", j["job"]
    assert j["results"]["booklets"] == 2 and j["results"]["ready"] == 0 and j["results"]["notes"] == []

    res = client.get(f"/api/scans/results?{q(demo)}").get_json()
    bs = res["booklets"]
    assert bs[0]["missing"] == [] and all(len(b["pages"]) + len(b["missing"]) == 4 for b in bs), [b["missing"] for b in bs]   # its pages: read, or missing
    for b, who in zip(bs, people):        # never the wrong student without a person; an unsure one, a person picks
        if b["student"]["status"] == "auto":
            assert b["student"]["num"] == who["num"], b["student"]
        else:
            assert b["student"]["status"] == "check"
            r = client.post("/api/scans/review", json={"offering": demo["offering"], "exam": "midterm", "booklet": b["key"], "student": who["num"]}, headers=H)
            assert r.status_code == 200 and r.get_json()["booklet"]["student"]["status"] == "done"
    bs = client.get(f"/api/scans/results?{q(demo)}").get_json()["booklets"]
    assert [b["student"]["num"] for b in bs] == [people[0]["num"], people[1]["num"]]
    one = {x["label"]: x for x in bs[0]["questions"]}
    assert one["8"]["status"] == "manual" and one["10"]["status"] == "manual" and one["1"]["score"] == 2
    two = {x["label"]: x for x in bs[1]["questions"]}
    assert two["1"]["score"] == 0 and two["2"]["score"] == 0
    pic = client.get(one["4"]["picture"])
    assert pic.status_code == 200 and pic.data[:2] == b"\xff\xd8"

    # A question with two blanks: each its own row, worth its own mark; the number is marked, the word waits for a person.
    ten = one["10"]
    assert [x["kind"] for x in ten["blanks"]] == ["blank", "num"] and [x["points"] for x in ten["blanks"]] == [1, 1]
    assert ten["blanks"][0]["status"] == "manual" and ten["blanks"][1]["score"] == 1
    assert client.get(ten["blanks"][1]["picture"]).data[:2] == b"\xff\xd8"
    rb = lambda b, **kw: client.post("/api/scans/review", json={"offering": demo["offering"], "exam": "midterm", "booklet": b["key"], "label": "10", **kw}, headers=H)
    r = rb(bs[0], blank=ten["blanks"][0]["id"], read="ottawa")
    assert r.status_code == 200, r.get_json()
    t = next(x for x in r.get_json()["booklet"]["questions"] if x["label"] == "10")
    assert t["status"] == "done" and t["score"] == 2 and t["blanks"][0]["typed"] and t["blanks"][0]["score"] == 1
    t2 = two["10"]
    r = rb(bs[1], blank=t2["blanks"][0]["id"], read="Toronto")
    t2 = next(x for x in r.get_json()["booklet"]["questions"] if x["label"] == "10")
    assert t2["blanks"][0]["score"] == 0
    if t2["blanks"][1]["status"] == "check":       # the grader wasn't sure of "12": a person says it is
        t2 = next(x for x in rb(bs[1], blank=t2["blanks"][1]["id"], keep=True).get_json()["booklet"]["questions"] if x["label"] == "10")
    assert t2["status"] == "done" and t2["score"] == 0, t2
    assert rb(bs[1], blank=t2["blanks"][1]["id"], score=2).status_code == 400          # more than the blank is worth
    t2 = next(x for x in rb(bs[1], blank=t2["blanks"][1]["id"], score=0.5).get_json()["booklet"]["questions"] if x["label"] == "10")
    assert t2["score"] == 0.5 and t2["blanks"][1]["score"] == 0.5
    t2 = next(x for x in rb(bs[1], blank=t2["blanks"][1]["id"], score=0).get_json()["booklet"]["questions"] if x["label"] == "10")
    assert t2["score"] == 0
    whats = [h["what"] for h in t2["history"]]                                     # every change, who and when
    assert whats[0] == "Blank 1: read as “Toronto” (was “”)" and "Blank 2: score 0.5 of 1" in whats and all(h["by"] and h["at"] for h in t2["history"]), whats
    bs = client.get(f"/api/scans/results?{q(demo)}").get_json()["booklets"]

    # Comments: the grader's for what it marked down; the rubric's set the score; a new one goes into the exam.
    assert [c["text"] for c in two["2"]["auto"]] == ["Incorrect answer selected"] and two["2"]["auto"][0]["delta"] == -1
    assert one["1"]["auto"] == [] and one["8"]["comments"] == []
    lines = {c["text"][:5]: c["id"] for c in client.get(f"/api/scans/results?{q(demo)}").get_json()["rubrics"][one["8"]["id"]]["lines"]}
    rq = lambda b, **kw: client.post("/api/scans/review", json={"offering": demo["offering"], "exam": "midterm", "booklet": b["key"], "label": "8", **kw}, headers=H)
    e8 = next(x for x in rq(bs[0], rubric=[lines["Says "]]).get_json()["booklet"]["questions"] if x["label"] == "8")
    assert e8["score"] == 1 and e8["status"] == "done" and [c["delta"] for c in e8["comments"]] == [1]      # from zero, +1
    e8 = next(x for x in rq(bs[0], rubric=[lines["Says "], lines["Adds "]], note="Nicely put.").get_json()["booklet"]["questions"] if x["label"] == "8")
    assert e8["score"] == 3 and e8["forStudent"] == "Nicely put."
    r = client.post("/api/scans/comment", json={"offering": demo["offering"], "exam": "midterm", "booklet": bs[0]["key"], "label": "8", "text": "Uses an example, not a proof", "delta": -1}, headers=H)
    assert r.status_code == 200, r.get_json()
    e8 = next(x for x in r.get_json()["booklet"]["questions"] if x["label"] == "8")
    assert e8["score"] == 2 and [c["text"] for c in e8["comments"]][-1] == "Uses an example, not a proof"
    saved = json.loads(store.Repo(user["id"], "priv").read(f"{demo['offering']}/midterm/exam.json"))
    assert any(c["text"] == "Uses an example, not a proof" and c["delta"] == -1 for c in grade.find_node(saved, one["8"]["id"])["rubric"])
    e8 = next(x for x in rq(bs[0], rubric=[]).get_json()["booklet"]["questions"] if x["label"] == "8")
    assert e8["status"] == "manual" and e8["score"] is None and e8["forStudent"] == "Nicely put."                 # taken back: a note stays
    bs = client.get(f"/api/scans/results?{q(demo)}").get_json()["booklets"]

    # Review: written answers marked; anything the grader left to check confirmed at its score.
    assert all(x["score"] == x["points"] for x in bs[0]["questions"] if x["status"] == "auto")   # nothing marked down wrongly
    for i, b in enumerate(bs):
        for x in b["questions"]:
            if x["status"] != "auto":     # a person looks: the first booklet is all right; the second as read
                s = x["points"] if i == 0 else {"8": 1, "10": 0}.get(x["label"], x["score"] or 0)
                r = client.post("/api/scans/review", json={"offering": demo["offering"], "exam": "midterm", "booklet": b["key"], "label": x["label"], "score": s}, headers=H)
                assert r.status_code == 200, r.get_json()
    over = client.post("/api/scans/review", json={"offering": demo["offering"], "exam": "midterm", "booklet": bs[0]["key"], "label": "8", "score": 4}, headers=H)
    assert over.status_code == 400
    j = client.get(f"/api/scans?{q(demo)}").get_json()
    assert j["results"]["ready"] == 2
    after = client.get(f"/api/scans/results?{q(demo)}").get_json()["booklets"]
    totals = {b["student"]["num"]: b["total"] for b in after}

    # The booklet as its student gets it: a PDF with the marking drawn on.
    pdf2 = client.get(f"/api/scans/annotated?{q(demo)}&booklet={after[1]['key']}&answers=1")
    assert pdf2.status_code == 200 and pdf2.data[:4] == b"%PDF", pdf2.data[:200]
    if os.environ.get("LECTERN_KEEP_PDF"):
        open(os.environ["LECTERN_KEEP_PDF"], "wb").write(pdf2.data)

    # Send: the demo already has Test 1 marks, so they differ and wait to be replaced.
    r = client.post("/api/scans/send", json={"offering": demo["offering"], "exam": "midterm"}, headers=H).get_json()
    assert r["sent"] == 0 and len(r["differ"]) == 2
    r = client.post("/api/scans/send", json={"offering": demo["offering"], "exam": "midterm", "replace": True}, headers=H).get_json()
    assert r["sent"] == 2
    book = json.loads(store.Repo(user["id"], "priv").read(f"{demo['offering']}/grades.json"))
    for num, tot in totals.items():
        assert book["marks"][num]["mt"] == {"pts": tot}
    assert totals[people[0]["num"]] == 22

    # Each student their booklet, marked, by email: a PDF each, and the booklets say so.
    from server import mailer
    mailer.sent.clear()
    r = client.post("/api/scans/email", json={"offering": demo["offering"], "exam": "midterm", "answers": True}, headers=H)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["emailing"] == 2, r.get_json()
    got = [m for m in mailer.sent if m["files"]]
    assert len(got) == 2 and all(m["files"][0][0].endswith(".pdf") and m["files"][0][1] > 10000 for m in got), mailer.sent
    assert "marked" in got[0]["subject"] and "out of 22" in got[0]["body"]
    j = client.get(f"/api/scans?{q(demo)}").get_json()
    assert j["results"]["emailed"] == 2 and j["results"]["mail"]["state"] == "done" and j["results"]["mail"]["answers"]
    assert all(b["emailed"] for b in client.get(f"/api/scans/results?{q(demo)}").get_json()["booklets"])

    # A student's own marked booklet, from the course page: only theirs, only to them, only when it's out.
    my_booklet_from_the_course_page(client, user, demo, people, totals)

    # Delete everything: the scans, results and printed copy go.
    assert client.post("/api/scans/delete", json={"offering": demo["offering"], "exam": "midterm", "all": True}, headers=H).status_code == 200
    j = client.get(f"/api/scans?{q(demo)}").get_json()
    assert j["uploads"] == [] and not j["results"] and j["copies"][0]["printed"] is None


def test_who_may_do_what(client, user, demo):
    off = demo["offering"]
    ta = app.test_client()
    make_user(ta, email="ta@utoronto.ca", name="Tia", handle="tia")
    stranger = app.test_client()
    make_user(stranger, email="x@utoronto.ca", name="Xan", handle="xan")
    r = client.post(f"/api/teams/chandra/{off}/add", json={"email": "ta@utoronto.ca", "role": "ta"}, headers=H)
    tok = r.get_json()["link"].split("#join=")[1]
    assert ta.post("/api/teams/join", json={"token": tok}, headers=H).status_code == 200
    qq = f"owner=chandra&offering={off}&exam=midterm"
    j = ta.get(f"/api/scans?{qq}").get_json()
    assert j["role"] == "ta" and j["can"] == {"print": False, "upload": False, "mark": True}
    assert ta.get(f"/api/scans/pdf?{qq}&doc=key").status_code == 200
    assert ta.get(f"/api/scans/pdf?{qq}&doc=student&print=1").status_code == 403
    up = ta.post(f"/api/scans/upload?{qq}", data={"file": (io.BytesIO(b"%PDF-1.4"), "a.pdf")}, headers=H, content_type="multipart/form-data")
    assert up.status_code == 403
    assert ta.post("/api/scans/delete", json={"owner": "chandra", "offering": off, "exam": "midterm", "all": True}, headers=H).status_code == 403
    assert stranger.get(f"/api/scans?{qq}").status_code == 404
    assert stranger.get(f"/api/scans/pdf?{qq}").status_code == 404
    assert client.get(f"/api/scans/picture?offering={off}&exam=midterm&name=../../grades.json").status_code == 404

    # Graders: who marks a question. The owner chooses (a TA can't); a TA then can't mark one that's someone else's.
    marks = {m["name"]: m for m in j["markers"]}
    assert marks["Tia"]["role"] == "ta" and j["graders"] == {}
    me = client.get(f"/api/scans?{qq}").get_json()["me"]
    body = lambda **kw: {"owner": "chandra", "offering": off, "exam": "midterm", **kw}
    assert ta.post("/api/scans/graders", json=body(label="8", users=[marks["Tia"]["id"]]), headers=H).status_code == 403
    assert client.post("/api/scans/graders", json=body(label="99", users=[me]), headers=H).status_code == 400
    r = client.post("/api/scans/graders", json=body(label="8", users=[me, 12345]), headers=H)
    assert r.status_code == 200 and r.get_json()["graders"] == {"8": [me]}, r.get_json()      # only people on the team
    assert ta.get(f"/api/scans?{qq}").get_json()["graders"] == {"8": [me]}
    import json as _json
    d = os.path.join(os.environ["LECTERN_DATA_DIR"], "scans", str(me), *off.split("/"), "midterm")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "results.json"), "w") as f:     # one booklet, so there's something to mark
        _json.dump({"booklets": [{"pages": ["a.pdf p.1"], "questions": [{"label": "8", "points": 3, "status": "manual", "score": None}, {"label": "9(a)", "points": 1, "status": "manual", "score": None}]}]}, f)
    no = ta.post("/api/scans/review", json=body(booklet="a.pdf p.1", label="8", score=1), headers=H)
    assert no.status_code == 403 and "other graders" in no.get_json()["error"], no.get_json()
    assert ta.post("/api/scans/review", json=body(booklet="a.pdf p.1", label="9(a)", score=1), headers=H).status_code != 403   # nobody's on it: anyone
    assert client.post("/api/scans/graders", json=body(label="8", users=[]), headers=H).get_json()["graders"] == {}


def test_numbered_booklets(client, user, demo):
    """Printed as numbered booklets: each number once, carrying on from the last printed."""
    import pypdfium2
    one = client.get(f"/api/scans/pdf?{q(demo, doc='student', print=1)}")
    assert one.status_code == 200
    pages = len(pypdfium2.PdfDocument(one.data))
    assert client.get(f"/api/scans?{q(demo)}").get_json()["nextBooklet"] == 1
    r = client.get(f"/api/scans/pdf?{q(demo, doc='student', print=1, booklets=3)}")
    assert r.status_code == 200 and r.data[:4] == b"%PDF", r.get_json()
    assert len(pypdfium2.PdfDocument(r.data)) == 3 * pages
    r = client.get(f"/api/scans/pdf?{q(demo, doc='student', print=1, booklets=2)}")
    j = client.get(f"/api/scans?{q(demo)}").get_json()
    assert j["copies"][0]["printed"]["booklets"] == [[1, 3], [4, 5]] and j["nextBooklet"] == 6
    assert client.get(f"/api/scans/pdf?{q(demo, doc='student', booklets=2)}").status_code == 400      # only printed
    assert client.get(f"/api/scans/pdf?{q(demo, doc='student', print=1, booklets=0)}").status_code == 400


def test_latex_stays_in_its_folder(client, user, demo):
    """An exam's LaTeX can't read files outside its folder (or run commands)."""
    repo = store.Repo(user["id"], "priv")
    off = demo["offering"]
    evil = (r"\documentclass{article}\begin{document}\input{/etc/hostname}\end{document}").encode()
    repo.commit({f"{off}/midterm/midterm-key.tex": evil}, "evil", repo.head())
    r = client.get(f"/api/scans/pdf?offering={off}&exam=midterm&doc=key")
    assert r.status_code == 422 and "LaTeX" in r.get_json()["error"]
    shell = (r"\documentclass{article}\begin{document}\immediate\write18{touch pwned}x\end{document}").encode()
    repo.commit({f"{off}/midterm/midterm-guide.tex": shell}, "evil", repo.head())
    r = client.get(f"/api/scans/pdf?offering={off}&exam=midterm&doc=guide")
    assert r.status_code == 200          # \write18 is ignored: the PDF is made, nothing runs


def test_without_latex(client, user, demo, monkeypatch):
    monkeypatch.setattr(scanning.shutil, "which", lambda name: None)
    r = client.get(f"/api/scans/pdf?offering={demo['offering']}&exam=midterm&doc=key")
    assert r.status_code == 503 and "LaTeX" in r.get_json()["error"]
    assert client.get(f"/api/scans?offering={demo['offering']}&exam=midterm").get_json()["latex"] is False


def my_booklet_from_the_course_page(client, user, demo, people, totals):
    from server import mailer, scanning as S
    from test_students import code_for
    course, term = demo["offering"].split("/")
    hub = f"/api/hub/chandra/{course}/{term}"
    repo = store.Repo(user["id"], "priv")

    def edit(fn):
        text, sha = repo.read_text(f"{demo['offering']}/grades.json")
        b = json.loads(text)
        fn(b)
        repo.write_text(f"{demo['offering']}/grades.json", json.dumps(b), sha, "test")

    book = json.loads(repo.read(f"{demo['offering']}/grades.json"))
    email = lambda s: (s.get("f") or {}).get("email") or s.get("email")
    edit(lambda b: [s.setdefault("f", {}).__setitem__("email", f"s{s['num']}@mail.utoronto.ca") for s in b["students"] if not email(s)])
    book = json.loads(repo.read(f"{demo['offering']}/grades.json"))
    nums = {p["num"] for p in people}
    a, b2 = (next(s for s in book["students"] if s["num"] == p["num"]) for p in people)
    other = next(s for s in book["students"] if s["num"] not in nums and not s.get("dropped"))

    def student(s):
        c = app.test_client()
        assert c.post(f"{hub}/code", json={"email": email(s)}, headers=H).status_code == 200
        r = c.post(f"{hub}/verify", json={"email": email(s), "code": code_for(email(s))}, headers=H)
        assert r.status_code == 200, r.get_json()
        return c

    def ask(c, **d):
        mailer.sent.clear()
        return c.post(f"{hub}/booklet", json={"e": "mt", **d}, headers=H)

    sa, sb, so = student(a), student(b2), student(other)
    assert app.test_client().post(f"{hub}/booklet", json={"e": "mt"}, headers=H).status_code == 401      # not signed in
    assert sa.post(f"{hub}/booklet", json={"e": "mt"}).status_code == 403                                  # not from Lectern's page
    assert ask(sa, e="../mt").status_code == 400

    def refused(c):
        r = ask(c)
        assert r.status_code == 403 and r.get_json()["error"] == S._NOT_HERE, r.get_json()
        assert not mailer.sent

    edit(lambda b: next(e for e in b["evals"] if e["id"] == "mt").pop("released", None))
    refused(sa)                                                         # marks not out, booklets off
    edit(lambda b: next(e for e in b["evals"] if e["id"] == "mt").update(booklets=True))
    refused(sa)                                                         # booklets on, marks not out
    edit(lambda b: next(e for e in b["evals"] if e["id"] == "mt").update(released=True, booklets=False))
    refused(sa)                                                         # marks out, booklets off
    assert "booklet" not in (sa.get(hub).get_json()["viewer"]["marks"].get("mt") or {})
    edit(lambda b: next(e for e in b["evals"] if e["id"] == "mt").update(booklets=True))
    assert sa.get(hub).get_json()["viewer"]["marks"]["mt"] == {"pts": totals[a["num"]], "booklet": True}

    # Theirs, to the class list's address, whatever else the request says.
    r = ask(sa, num=b2["num"], email="someone@else.com", to="someone@else.com", booklet="x", answers=True)
    assert r.status_code == 200 and r.get_json()["email"] == email(a).lower(), r.get_json()
    got = [m for m in mailer.sent if m["files"]]
    assert len(got) == 1 and got[0]["to"] == email(a).lower() and a["num"] in got[0]["files"][0][0], mailer.sent
    assert f"out of" in got[0]["body"] and f"You got {totals[a['num']]:g}" in got[0]["body"]
    assert ask(sb).get_json()["email"] == email(b2).lower() and b2["num"] in mailer.sent[-1]["files"][0][0]

    refused(so)                                                         # on the class list, with no booklet
    edit(lambda b: b["marks"].setdefault(other["num"], {}).update(mt={"pts": 5}))
    refused(so)                                                         # a mark, but no booklet of theirs

    # Their mark isn't this booklet's total (changed in the gradebook): not sent.
    edit(lambda b: b["marks"][a["num"]].update(mt={"pts": totals[a["num"]] - 1}))
    refused(sa)
    edit(lambda b: b["marks"][a["num"]].update(mt={"pts": totals[a["num"]]}))

    # A few a day each.
    assert ask(sa).status_code == 200 and ask(sa).status_code == 200      # 3 today with the one above
    r = ask(sa)
    assert r.status_code == 429 and not mailer.sent
    edit(lambda b: next(s for s in b["students"] if s["num"] == b2["num"]).update(dropped=True))
    r = ask(sb)
    assert r.status_code == 401 and not mailer.sent                   # dropped from the class: signed out
