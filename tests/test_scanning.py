"""An exam's Print and Scan page (server/scanning.py): its PDFs, uploading scans, marking them, the team's review,
and sending the marks to the gradebook, on the demo course's midterm (which has Marking from scans on).

The scans are made as in test_autograde: the printed PDF's pages, written on and "scanned". (Skipped without
pdflatex, node, or the scan packages.)
"""
import io
import json
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
    assert j["exam"]["scan"] and j["exam"]["total"] == 21 and j["copies"][0]["printed"] is None and j["latex"]
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
            f"{L['9(a)']['id']}.{right(L['9(a)'])}": "fill", f"{L['9(b)']['id']}:T": "fill", f"{L['9(c)']['id']}.{comp(L['9(c)'], 'num')}": "30"}
    wrong = {k: v for k, v in good.items() if not k.startswith(L["1"]["id"]) and not k.startswith(L["2"]["id"])}
    wrong[f"{L['2']['id']}:F"] = "fill"
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

    r = client.post("/api/scans/mark", json={"offering": demo["offering"], "exam": "midterm"}, headers=H)
    assert r.status_code == 200, r.get_json()
    j = wait_marked(client, demo)
    assert j["job"]["state"] == "done", j["job"]
    assert j["results"]["booklets"] == 2 and j["results"]["ready"] == 0 and j["results"]["notes"] == []

    res = client.get(f"/api/scans/results?{q(demo)}").get_json()
    bs = res["booklets"]
    assert [b["student"]["num"] for b in bs] == [people[0]["num"], people[1]["num"]]
    assert all(b["student"]["status"] == "auto" for b in bs)
    one = {x["label"]: x for x in bs[0]["questions"]}
    assert one["8"]["status"] == "manual" and one["10"]["status"] == "manual" and one["1"]["score"] == 2
    two = {x["label"]: x for x in bs[1]["questions"]}
    assert two["1"]["score"] == 0 and two["2"]["score"] == 0
    pic = client.get(one["4"]["picture"])
    assert pic.status_code == 200 and pic.data[:2] == b"\xff\xd8"

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

    # Send: the demo already has Test 1 marks, so they differ and wait to be replaced.
    r = client.post("/api/scans/send", json={"offering": demo["offering"], "exam": "midterm"}, headers=H).get_json()
    assert r["sent"] == 0 and len(r["differ"]) == 2
    r = client.post("/api/scans/send", json={"offering": demo["offering"], "exam": "midterm", "replace": True}, headers=H).get_json()
    assert r["sent"] == 2
    book = json.loads(store.Repo(user["id"], "priv").read(f"{demo['offering']}/grades.json"))
    for num, tot in totals.items():
        assert book["marks"][num]["mt"] == {"pts": tot}
    assert totals[people[0]["num"]] == 21

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
