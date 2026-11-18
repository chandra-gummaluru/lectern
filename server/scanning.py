"""Exams on paper: their PDFs, and marking them from scans (an exam's Print and Scan page in Lectern).

PDFs. The Exam Builder saves each exam's .tex files (student copy, answer key, marking guide, one set per version)
into the offering's private files; here the server compiles them with pdflatex, on request. LaTeX runs as a
guest: no shell commands (-no-shell-escape), reading and writing only in its own folder (openin_any=p,
openout_any=p: no absolute paths, no ..), limited in time and memory. PDFs are kept by what they're made from
(data/latex/cache), so asking again is instant.

Marking. With "Marking from scans" on (the builder's Settings), the student copy has corner squares, a QR code
per page and invisible tags on every answer piece (course.cls v2.6). Then:
  1. Print: the student copy's PDF, downloaded for printing, is kept as the printed copy: scans are always
     marked against exactly what was printed (if the exam is changed after, the page says so).
  2. Scans: the scanned PDFs (or images) are uploaded, one file at a time, any number.
  3. Mark: server/autograde reads them, in a background thread (progress in job.json), and keeps its results and
     the pictures of each answer.
  4. Review: the team confirms or corrects what the grader wasn't sure of, and marks what it can't (written
     answers): each decision is kept in review.json, apart from the grader's results, so marking again (more
     scans) keeps them.
  5. Send: each booklet that's finished (its student known, every question marked) becomes the student's mark
     for the exam's evaluation in the gradebook (exam.json's settings.link).

All of it is kept outside the offering's files, in data/scans/<owner id>/<course>/<term>/<exam>/ (printed/,
uploads/, results.json, pictures/, review.json, job.json): students' scans aren't versioned, exported or counted
in the account's space, and Delete Everything removes them.

Who: anyone on the offering's teaching team sees the page; its owner and coordinators print the copy that's
marked against, upload, mark and delete; they and TAs review and send marks (a TA enters marks anyway).

  GET  /api/scans?owner&offering&exam                    the exam, its printed copies, scans, marking, results
  GET  /api/scans/pdf?…&doc=student|key|guide&v=A[&print=1]   a PDF (print=1: kept as the printed student copy)
  POST /api/scans/upload?owner&offering&exam   (a file)   a scanned PDF or image
  POST /api/scans/delete  {owner, offering, exam, file | all}
  POST /api/scans/mark    {owner, offering, exam}         mark every uploaded scan (in the background)
  GET  /api/scans/results?owner&offering&exam             every booklet, with what was read and decided
  GET  /api/scans/picture?owner&offering&exam&name
  POST /api/scans/review  {owner, offering, exam, booklet, student? | label + score}
  POST /api/scans/send    {owner, offering, exam, replace}
"""
import functools
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time

from flask import Blueprint, Response, g, jsonify, request, send_file

from . import db
from .accommodations import Refusal, _err, _offering, _owner
from .auth import signed_in
from .store import Repo, StoreError

scans_bp = Blueprint("scans", __name__)

ROLES = ("owner", "coordinator", "instructor", "ta", "staff")
LEADS = ("owner", "coordinator")
MARKERS = ("owner", "coordinator", "ta")
LET = "ABCDEF"
DOCS = {"student": "", "key": "-key", "guide": "-guide"}
_SLUG = re.compile(r"^[\w.-]{1,64}$")
SCAN_TYPES = {".pdf": b"%PDF", ".png": b"\x89PNG", ".jpg": b"\xff\xd8", ".jpeg": b"\xff\xd8", ".tif": None, ".tiff": None}
MAX_SCAN_MB = int(os.environ.get("LECTERN_MAX_SCAN_MB") or 1024)
LATEX_RUNS = threading.BoundedSemaphore(int(os.environ.get("LECTERN_LATEX_AT_ONCE") or 2))
LATEX_TIMEOUT = 120
CACHE_DAYS = 14


def team_api(fn):
    @signed_in
    @functools.wraps(fn)
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except Refusal as x:
            return _err(x)
        except StoreError as x:
            return _err(Refusal(x.status, str(x)))
    return run


class Exam:
    """The exam a request is about, and who's asking."""
    def __init__(self, d, need=ROLES):
        from .teams import role_of
        self.o = _offering(d.get("offering"))
        self.owner = _owner(d.get("owner")) if d.get("owner") else g.user["id"]
        self.role = role_of(g.user["id"], self.owner, self.o)
        if self.role not in ROLES:
            raise Refusal(404, "That exam isn't there.")
        if self.role not in need:
            raise Refusal(403, {LEADS: "Only the offering's owner and coordinators can do that.",
                                MARKERS: "Only the offering's owner, coordinators and TAs can mark."}.get(need, "You can't do that here."))
        self.e = str(d.get("exam") or "")
        if not _SLUG.match(self.e) or self.e[0] in "._":
            raise Refusal(400, "Which exam?")
        self.repo = Repo(self.owner, "priv")
        self.src = os.path.join(self.repo.root, *self.o.split("/"), self.e)
        raw = self.repo.read(f"{self.o}/{self.e}/exam.json")
        if raw is None:
            raise Refusal(404, "That exam isn't there (or isn't saved yet).")
        try:
            self.exam = json.loads(raw)
        except ValueError:
            raise Refusal(422, "The exam's exam.json can't be read.")
        self.settings = self.exam.get("settings") or {}
        self.dir = os.path.join(db.data_dir(), "scans", str(self.owner), *self.o.split("/"), self.e)

    @property
    def versions(self):
        try:
            n = int(self.settings.get("versions") or 1)
        except (TypeError, ValueError):
            n = 1
        return max(1, min(6, n))

    def bases(self):
        """[(version letter or "", the student copy's .tex name without .tex)]: as the builder names them."""
        n = self.versions
        return [(LET[i], f"{self.e}-{LET[i]}") if n > 1 else ("", self.e) for i in range(n)]

    def base(self, v):
        for letter, b in self.bases():
            if letter == (v or "").upper() or not letter:
                return b
        raise Refusal(400, "Which version?")

    def path(self, *p):
        return os.path.join(self.dir, *p)

    def read_json(self, name, default):
        try:
            with open(self.path(name), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def write_json(self, name, data):
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.path(name))


def _args():
    return (request.get_json(silent=True) or {}) if request.method == "POST" and request.is_json else request.args


def _sha_file(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


# ── PDFs ─────────────────────────────────────────────────────────────

def latex_ok():
    return bool(shutil.which("pdflatex"))


def _inputs(src):
    """The exam folder's files (relative path → bytes): what LaTeX may read. Links and big things are left out."""
    out, total = {}, 0
    for dp, dns, fns in os.walk(src):
        dns[:] = [d for d in dns if not d.startswith(".") and not os.path.islink(os.path.join(dp, d))]
        for fn in fns:
            full = os.path.join(dp, fn)
            if os.path.islink(full) or not os.path.isfile(full) or fn.endswith(".lectern-tmp"):
                continue
            size = os.path.getsize(full)
            total += size
            if total > 200 * 1024 * 1024:
                raise Refusal(413, "The exam's folder is too big to make a PDF from.")
            with open(full, "rb") as f:
                out[os.path.relpath(full, src).replace(os.sep, "/")] = f.read()
    return out


def _limits():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (LATEX_TIMEOUT, LATEX_TIMEOUT + 5))
        resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
    except (ImportError, ValueError, OSError):
        pass


def _latex_error(log):
    lines = log.splitlines()
    for i, l in enumerate(lines):
        if l.startswith("!"):
            more = [x for x in lines[i + 1:i + 3] if x.strip()]
            return " ".join([l[1:].strip()] + [x.strip() for x in more])[:400]
    return "it stopped without saying why"


def build_pdf(src, tex):
    """The PDF of src/tex (bytes), made by pdflatex (twice: the points table and page count need it), or from the cache."""
    if not latex_ok():
        raise Refusal(503, "This Lectern can't make PDFs: its server doesn't have LaTeX (pdflatex). Ask whoever runs it to install TeX Live.")
    files = _inputs(src)
    if tex not in files:
        raise Refusal(404, f"{tex} isn't there yet: save the exam in the Exam Builder first.")
    h = hashlib.sha256(tex.encode())
    for name in sorted(files):
        h.update(name.encode() + b"\0" + hashlib.sha256(files[name]).digest())
    cache = os.path.join(db.data_dir(), "latex", "cache")
    hit = os.path.join(cache, h.hexdigest() + ".pdf")
    if os.path.isfile(hit):
        os.utime(hit)
        with open(hit, "rb") as f:
            return f.read()
    var = os.path.join(db.data_dir(), "latex", "var")      # LaTeX's own caches (fonts it makes), kept between runs
    os.makedirs(var, exist_ok=True)
    with LATEX_RUNS, tempfile.TemporaryDirectory(prefix="lectern-tex-") as tmp:
        for name, data in files.items():
            full = os.path.join(tmp, *name.split("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(data)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmp, "LANG": "C.UTF-8",
               "openin_any": "p", "openout_any": "p", "shell_escape": "f", "TEXMFVAR": var, "TEXMFOUTPUT": tmp}
        cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", tex]
        for _ in range(2):
            try:
                subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, timeout=LATEX_TIMEOUT,
                               preexec_fn=_limits if os.name == "posix" else None)
            except subprocess.TimeoutExpired:
                raise Refusal(422, "LaTeX took too long to make the PDF.")
        out = os.path.join(tmp, tex[:-4] + ".pdf")
        log = ""
        try:
            with open(os.path.join(tmp, tex[:-4] + ".log"), encoding="latin-1") as f:
                log = f.read()
        except OSError:
            pass
        if not os.path.isfile(out) or "\n!" in "\n" + log:
            raise Refusal(422, f"LaTeX couldn't make the PDF: {_latex_error(log)}")
        with open(out, "rb") as f:
            pdf = f.read()
    os.makedirs(cache, exist_ok=True)
    tmpc = hit + f".{os.getpid()}.tmp"
    with open(tmpc, "wb") as f:
        f.write(pdf)
    os.replace(tmpc, hit)
    _prune_cache(cache)
    return pdf


def _prune_cache(cache):
    old = time.time() - CACHE_DAYS * 86400
    try:
        for fn in os.listdir(cache):
            p = os.path.join(cache, fn)
            if os.path.getmtime(p) < old:
                os.remove(p)
    except OSError:
        pass


@scans_bp.get("/api/scans/pdf")
@team_api
def pdf():
    d = request.args
    ex = Exam(d)
    doc = d.get("doc") or "student"
    if doc not in DOCS:
        raise Refusal(400, "Which PDF?")
    if d.get("print") and (doc != "student" or ex.role not in LEADS):
        raise Refusal(403, "Only the offering's owner and coordinators print the copy that's marked.")
    base = ex.base(d.get("v"))
    data = build_pdf(ex.src, f"{base}{DOCS[doc]}.tex")
    if d.get("print"):
        os.makedirs(ex.path("printed"), exist_ok=True)
        with open(ex.path("printed", base + ".pdf"), "wb") as f:
            f.write(data)
        meta = ex.read_json("printed.json", {})
        meta[base] = {"at": time.time(), "by": g.user["name"], "tex": _sha_file(os.path.join(ex.src, base + ".tex"))}
        ex.write_json("printed.json", meta)
    title = re.sub(r"[^\w.-]+", "-", f"{ex.o.replace('/', '-')}-{base}{DOCS[doc]}")
    return send_file(io.BytesIO(data), mimetype="application/pdf", as_attachment=bool(d.get("download")),
                     download_name=f"{title}.pdf", max_age=0)


# ── Scans ────────────────────────────────────────────────────────────

def _uploads(ex):
    p = ex.path("uploads")
    if not os.path.isdir(p):
        return []
    meta = ex.read_json("uploads.json", {})
    out = []
    for fn in sorted(os.listdir(p)):
        full = os.path.join(p, fn)
        if os.path.isfile(full) and not fn.endswith(".tmp"):
            m = meta.get(fn, {})
            out.append({"file": fn, "name": m.get("name") or fn, "size": os.path.getsize(full), "pages": m.get("pages"),
                        "at": m.get("at") or os.path.getmtime(full), "by": m.get("by", "")})
    return out


def _pages(path):
    if not path.lower().endswith(".pdf"):
        return 1
    try:
        import pypdfium2
        doc = pypdfium2.PdfDocument(path)
        n = len(doc)
        doc.close()
        return n
    except Exception:
        return None


@scans_bp.post("/api/scans/upload")
@team_api
def upload():
    ex = Exam(request.args, LEADS)
    f = request.files.get("file")
    if not f or not f.filename:
        raise Refusal(400, "Choose a scanned PDF or image.")
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in SCAN_TYPES:
        raise Refusal(415, "Scans must be PDFs or images (PNG, JPEG or TIFF).")
    os.makedirs(ex.path("uploads"), exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "-", os.path.splitext(os.path.basename(f.filename))[0])[:60].strip("-.") or "scan"
    fn = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.urandom(3).hex()}-{safe}{ext}"
    full = ex.path("uploads", fn)
    f.save(full + ".tmp")
    head = open(full + ".tmp", "rb").read(8)
    magic = SCAN_TYPES[ext]
    if (magic and not head.startswith(magic)) or (magic is None and head[:4] not in (b"II*\0", b"MM\0*")):
        os.remove(full + ".tmp")
        raise Refusal(415, "That file isn't the PDF or image its name says.")
    os.replace(full + ".tmp", full)
    meta = ex.read_json("uploads.json", {})
    meta[fn] = {"name": os.path.basename(f.filename)[:120], "pages": _pages(full), "at": time.time(), "by": g.user["name"]}
    ex.write_json("uploads.json", meta)
    return jsonify(ok=True, files=_uploads(ex))


@scans_bp.post("/api/scans/delete")
@team_api
def delete():
    d = _args()
    ex = Exam(d, LEADS)
    if _running(ex):
        raise Refusal(409, "Wait until the marking finishes.")
    if d.get("all"):
        if os.path.isdir(ex.dir):
            shutil.rmtree(ex.dir)
        return jsonify(ok=True)
    fn = str(d.get("file") or "")
    if not re.match(r"^[\w.-]+$", fn) or not os.path.isfile(ex.path("uploads", fn)):
        raise Refusal(404, "That scan isn't there.")
    os.remove(ex.path("uploads", fn))
    meta = ex.read_json("uploads.json", {})
    meta.pop(fn, None)
    ex.write_json("uploads.json", meta)
    return jsonify(ok=True, files=_uploads(ex))


# ── Marking (in the background) ──────────────────────────────────────

_running_lock = threading.Lock()
_threads = {}


def _running(ex):
    job = ex.read_json("job.json", {})
    if job.get("state") != "running":
        return False
    return time.time() - job.get("beat", 0) < 180          # a server restart leaves a job that stopped beating


def _roster(ex):
    raw = ex.repo.read(f"{ex.o}/grades.json")
    try:
        book = json.loads(raw) if raw else {}
    except ValueError:
        book = {}
    return book, [s for s in book.get("students") or [] if isinstance(s, dict) and not s.get("dropped")]


def _templates(ex):
    """The student copies to mark against: the printed ones, else (with a warning) the current ones."""
    paths, notes = [], []
    os.makedirs(ex.path("work"), exist_ok=True)
    for letter, base in ex.bases():
        p = ex.path("printed", base + ".pdf")
        if not os.path.isfile(p):
            p = ex.path("work", base + ".pdf")
            with open(p, "wb") as f:
                f.write(build_pdf(ex.src, base + ".tex"))
            notes.append(f"{'Version ' + letter if letter else 'The student copy'} wasn't printed from here, so the scans were marked against the exam as it is now.")
        paths.append(p)
    return paths, notes


def _mark_job(ex, files, by):
    from .autograde import grade, report
    job = {"state": "running", "started": time.time(), "beat": time.time(), "by": by, "booklets": 0,
           "pages": sum((u.get("pages") or 0) for u in _uploads(ex))}
    ex.write_json("job.json", job)
    try:
        templates, notes = _templates(ex)
        _, roster = _roster(ex)

        def progress(n):
            job.update(booklets=n, beat=time.time())
            ex.write_json("job.json", job)

        res = grade.run(ex.exam, templates, files, roster, progress=progress)
        pics = ex.path(f"pictures-{int(time.time())}")
        report.save_pictures(res, pics, prefix="")
        res.update(notes=notes, marked=time.time(), pictures=os.path.basename(pics))
        old = ex.read_json("results.json", {}).get("pictures")
        ex.write_json("results.json", res)
        if old and old != res["pictures"] and os.path.isdir(ex.path(old)):
            shutil.rmtree(ex.path(old), ignore_errors=True)
        job.update(state="done", finished=time.time(), booklets=len(res["booklets"]), unread=len(res["unread"]))
    except Refusal as x:
        job.update(state="failed", error=str(x), finished=time.time())
    except Exception as x:                       # anything else: say so on the page, and keep the server going
        job.update(state="failed", error=f"The marking stopped: {x}", finished=time.time())
    ex.write_json("job.json", job)


@scans_bp.post("/api/scans/mark")
@team_api
def mark():
    ex = Exam(_args(), LEADS)
    if not ex.settings.get("scan"):
        raise Refusal(409, "Turn on Marking from scans in the exam's settings (and print it) first.")
    try:
        import numpy, cv2, pypdfium2, PIL  # noqa: F401
    except ImportError:
        raise Refusal(503, "This Lectern can't mark scans yet: its server needs the scan packages (pip install -r requirements-scan.txt).")
    files = [ex.path("uploads", u["file"]) for u in _uploads(ex)]
    if not files:
        raise Refusal(409, "Upload the scans first.")
    key = ex.dir
    with _running_lock:
        if _running(ex) or (key in _threads and _threads[key].is_alive()):
            raise Refusal(409, "They're being marked already.")
        t = threading.Thread(target=_mark_job, args=(ex, files, g.user["name"]), daemon=True, name="lectern-mark")
        _threads[key] = t
        ex.write_json("job.json", {"state": "running", "started": time.time(), "beat": time.time(), "by": g.user["name"], "booklets": 0})
        t.start()
    return jsonify(ok=True, job=ex.read_json("job.json", {}))


# ── Results and review ───────────────────────────────────────────────

def _key(b):
    return "|".join(b.get("pages") or [])


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) < 1e6 else None


def _where(pages, names):
    """A booklet's scanned pages, as people say them: "Class scan.pdf p.1–4" (pages are "<file> p.<n>")."""
    by = {}
    for p in pages or []:
        f, _, n = p.rpartition(" p.")
        by.setdefault(names.get(f, f), []).append(int(n) if n.isdigit() else n)
    out = []
    for name, ns in by.items():
        ints = sorted(x for x in ns if isinstance(x, int))
        runs, i = [], 0
        while i < len(ints):
            j = i
            while j + 1 < len(ints) and ints[j + 1] == ints[j] + 1:
                j += 1
            runs.append(f"{ints[i]}–{ints[j]}" if j > i else str(ints[i]))
            i = j + 1
        out.append(f"{name} p.{', '.join(runs)}" if runs else name)
    return "; ".join(out)


def view(ex, results, review, roster):
    """The booklets as the page shows them: the grader's reading with the team's decisions on top."""
    from .autograde.grade import nodes_of
    nodes = nodes_of(ex.exam)
    people = {str(s.get("num")): s for s in roster}
    names = {fn: m.get("name") or fn for fn, m in ex.read_json("uploads.json", {}).items()}
    name = lambda s: f"{s.get('first', '')} {s.get('last', '')}".strip()
    out = []
    counts = {}
    emailed = ex.read_json("mail.json", {}).get("sent") or {}
    for b in results.get("booklets") or []:
        k = _key(b)
        rv = (review.get("booklets") or {}).get(k) or {}
        st = dict(b.get("student") or {})
        st.pop("picture", None)
        if rv.get("student"):
            s = people.get(rv["student"]) or {}
            st.update(num=rv["student"], name=name(s), status="done", note="", by=rv.get("studentBy", ""))
        counts[st.get("num")] = counts.get(st.get("num"), 0) + 1 if st.get("num") else 0
        qs, total, open_ = [], 0.0, 0
        for q in b.get("questions") or []:
            q = dict(q)
            r = (rv.get("q") or {}).get(q["label"])
            if q.get("blanks"):
                _blanks(ex, results, q, (r or {}).get("blanks") or {})
            if r is not None and "score" in r:
                q.update(score=r.get("score"), status="done", by=r.get("by", ""), machine=q.get("score"), machineRead=q.get("read"))
                if "read" in r:
                    q.update(read=r["read"], typed=True)
            _comments(q, r, nodes)
            if q["status"] not in ("auto", "done"):
                open_ += 1
            total += q.get("score") or 0
            q["picture"] = _pic(ex, results, q.get("picture"))
            qs.append(q)
        out.append({"key": k, "pages": b.get("pages"), "where": _where(b.get("pages"), names), "version": b.get("version", ""), "student": st,
                    "cover": _pic(ex, results, (b.get("student") or {}).get("picture")),
                    "questions": qs, "total": round(total, 2), "out_of": b.get("out_of"), "open": open_, "emailed": emailed.get(k)})
    for b in out:            # one student in two booklets: neither is finished until a person says whose each is
        st = b["student"]
        if st.get("num") and counts.get(st["num"], 0) > 1 and st.get("status") != "done":
            st.update(status="check", note="More than one booklet matched this student.")
        b["ready"] = bool(st.get("num")) and st.get("status") in ("auto", "done") and b["open"] == 0
    return out


def _comments(q, r, nodes):
    """A question's comments for the student: the rubric comments a person gave (which set its score), or, where no
    person has scored it, what the grader says about what it marked down; and a person's note."""
    from .autograde.grade import auto_comments, plain
    node, _ = nodes.get(q.get("id"), (None, "full"))
    rub = {c.get("id"): c for c in (node or {}).get("rubric") or [] if c.get("id")}
    q["comments"] = [{"id": i, "text": plain(rub[i].get("text", "")), "delta": _num(rub[i].get("delta")) or 0} for i in (r or {}).get("rubric") or [] if i in rub]
    q["note"] = (r or {}).get("note", "")
    q["auto"] = [] if (r and "score" in r) or not node else auto_comments(node, q)


def _blanks(ex, results, q, dec):
    """A question with several blanks: each blank with the team's decision on top, then the question from its blanks
    (done once every blank is, unless it has room for working and a blank is wrong: then a person says if part marks are due)."""
    bl = []
    for x in q["blanks"]:
        x = dict(x)
        y = dec.get(x["id"])
        if y is not None:
            x.update(score=y.get("score"), status="done", by=y.get("by", ""), machine=x.get("score"))
            if "read" in y:
                x.update(read=y["read"], typed=True)
        x["picture"] = _pic(ex, results, x.get("picture"))
        bl.append(x)
    q["blanks"] = bl
    if not dec:
        return
    t = sum(x.get("score") or 0 for x in bl)
    t = round(t * 2) / 2 if q.get("even") else round(t, 2)
    if any(x["status"] == "manual" for x in bl):
        q.update(status="manual", score=None, note="", ask="")
    elif any(x["status"] == "check" for x in bl):
        q.update(status="check", score=t, note="", ask="")
    elif q.get("space") and any(not x.get("score") for x in bl):
        q.update(status="check", score=t, note="An answer is wrong. Is there working worth part marks?", ask="working")
    else:
        q.update(status="done", score=t, note="", ask="", by=next((x["by"] for x in reversed(bl) if x.get("by")), ""))


def _pic(ex, results, name):
    if not name:
        return None
    from urllib.parse import urlencode
    q = {"offering": ex.o, "exam": ex.e, "name": f"{results.get('pictures', '')}/{name}"}
    if ex.owner != g.user["id"]:
        q["owner"] = db.one("SELECT handle FROM users WHERE id = ?", (ex.owner,))["handle"]
    return "/api/scans/picture?" + urlencode(q)


@scans_bp.get("/api/scans")
@team_api
def overview():
    ex = Exam(request.args)
    book, roster = _roster(ex)
    ev = next((e for e in book.get("evals") or [] if e.get("id") == ex.settings.get("link")), None)
    printed = ex.read_json("printed.json", {})
    copies = []
    for letter, base in ex.bases():
        p = printed.get(base)
        if p and not os.path.isfile(ex.path("printed", base + ".pdf")):
            p = None
        copies.append({"version": letter, "base": base, "printed": p and {"at": p["at"], "by": p.get("by", ""),
                       "changed": p.get("tex") != _sha_file(os.path.join(ex.src, base + ".tex"))}})
    job = ex.read_json("job.json", {})
    if job.get("state") == "running" and not _running(ex):
        job = {**job, "state": "failed", "error": "The marking stopped (the server restarted?). Mark them again."}
    results = ex.read_json("results.json", {})
    review = ex.read_json("review.json", {})
    bs = view(ex, results, review, roster) if results else []
    mail = ex.read_json("mail.json", {})
    if mail.get("state") == "running" and time.time() - (mail.get("beat") or mail.get("started") or 0) > 600:
        mail = {**mail, "state": "failed", "error": "The emails stopped (the server restarted?). Email the rest again."}
    total = sum(_points(_first(it)) for it in ex.exam.get("items") or [] if it.get("kind") == "question")
    return jsonify(
        exam={"title": ex.settings.get("title") or ex.e, "scan": bool(ex.settings.get("scan")), "versions": ex.versions,
              "layout": ex.settings.get("layout") or "exam", "total": total},
        eval=ev and {"id": ev.get("id"), "name": ev.get("name") or ev.get("id"), "total": ev.get("total")},
        copies=copies, uploads=_uploads(ex), job=job, latex=latex_ok(), role=ex.role,
        can={"print": ex.role in LEADS, "upload": ex.role in LEADS, "mark": ex.role in MARKERS},
        results=None if not results else {"booklets": len(bs), "ready": sum(1 for b in bs if b["ready"]),
                             "open": sum(b["open"] for b in bs), "who": sum(1 for b in bs if b["student"].get("status") not in ("auto", "done")),
                             "unread": [{**u, "page": _where([u.get("page", "")], {fn: m.get("name") or fn for fn, m in ex.read_json("uploads.json", {}).items()})} for u in results.get("unread") or []], "notes": results.get("notes") or [], "marked": results.get("marked"),
                             "sent": review.get("sent"),
                             "mail": {k: v for k, v in mail.items() if k != "sent"} if mail else None,
                             "emailed": len(mail.get("sent") or {})})


def _points(n):
    parts = [p for p in n.get("parts") or [] if isinstance(p, dict)]
    return sum(_points(p) for p in parts) if parts else (_num(n.get("points")) or 0)


def _first(it):
    vs = it.get("variants") or [{}]
    return vs[0] if isinstance(vs[0], dict) else {}


@scans_bp.get("/api/scans/results")
@team_api
def results_():
    ex = Exam(request.args)
    _, roster = _roster(ex)
    results = ex.read_json("results.json", {})
    from .autograde.grade import nodes_of, plain
    rubrics = {nid: {"marking": mode, "lines": [{"id": c.get("id"), "text": plain(c.get("text", "")), "delta": _num(c.get("delta")) or 0} for c in n.get("rubric") or [] if c.get("id")]}
               for nid, (n, mode) in nodes_of(ex.exam).items()} if results else {}
    return jsonify(booklets=view(ex, results, ex.read_json("review.json", {}), roster) if results else [], rubrics=rubrics,
                   students=[{"num": str(s.get("num")), "first": s.get("first", ""), "last": s.get("last", "")} for s in roster])


@scans_bp.get("/api/scans/picture")
@team_api
def picture():
    ex = Exam(request.args)
    name = str(request.args.get("name") or "")
    if not re.match(r"^pictures-\d+/b\d{3}-[\w]+\.jpg$", name):
        raise Refusal(404, "No such picture.")
    p = ex.path(*name.split("/"))
    if not os.path.isfile(p):
        raise Refusal(404, "No such picture.")
    r = send_file(p, mimetype="image/jpeg", max_age=0)
    r.headers["Cache-Control"] = "private, max-age=3600"
    return r


@scans_bp.post("/api/scans/review")
@team_api
def review():
    d = _args()
    return review_with(Exam(d, MARKERS), d)


def review_with(ex, d):
    results = ex.read_json("results.json", {})
    k = str(d.get("booklet") or "")
    b = next((x for x in results.get("booklets") or [] if _key(x) == k), None)
    if not b:
        raise Refusal(404, "That booklet isn't in the results any more: reload the page.")
    with _running_lock:
        rv = ex.read_json("review.json", {})
        one = rv.setdefault("booklets", {}).setdefault(k, {})
        if "student" in d:
            num = str(d.get("student") or "")
            if num:
                _, roster = _roster(ex)
                if num not in {str(s.get("num")) for s in roster}:
                    raise Refusal(400, "That student isn't on the class list.")
                one.update(student=num, studentBy=g.user["name"])
            else:
                one.pop("student", None)
        if "label" in d:
            q = next((x for x in b.get("questions") or [] if x["label"] == d.get("label")), None)
            if not q:
                raise Refusal(404, "That question isn't in this booklet.")
            qd0 = one.setdefault("q", {}).setdefault(q["label"], {})
            if "note" in d:                     # a note for the student
                t = str(d.get("note") or "").strip()[:2000]
                qd0.update(note=t) if t else qd0.pop("note", None)
            if "rubric" in d:                   # the rubric comments given: they set the score
                from .autograde.grade import nodes_of, rubric_score
                node, mode = nodes_of(ex.exam).get(q.get("id"), (None, "full"))
                if not node:
                    raise Refusal(409, "That question has changed in the exam since it was marked.")
                lines = {c.get("id"): c for c in node.get("rubric") or [] if c.get("id")}
                ids = [i for i in dict.fromkeys(d.get("rubric") or []) if i in lines]
                if ids:
                    qd0.update(rubric=ids, score=rubric_score(node, mode, [lines[i].get("delta") for i in ids]), by=g.user["name"], at=time.time())
                else:
                    for k2 in ("rubric", "score", "read", "by", "at"):
                        qd0.pop(k2, None)
            elif d.get("blank"):                  # one blank of several: its reading, a yes to the grader's, or its own score
                from .autograde.grade import find_node, comps_of, blank_points, piece_right
                x = next((y for y in q.get("blanks") or [] if y["id"] == d["blank"]), None)
                node = find_node(ex.exam, q.get("id"))
                cs = comps_of(node) if node else []
                at = next((i for i, (cid, _) in enumerate(cs) if cid == d["blank"]), None)
                if not x or at is None:
                    raise Refusal(409, "That blank has changed in the exam since it was marked.")
                w = blank_points(node, [c for _, c in cs])[at]
                dec = one.setdefault("q", {}).setdefault(q["label"], {}).setdefault("blanks", {})
                mine = {"by": g.user["name"], "at": time.time()}
                if "read" in d:
                    text = str(d.get("read") or "")[:200].strip()
                    dec[x["id"]] = {"score": round(w, 4) if piece_right(cs[at][1], text) else 0.0, "read": text, **mine}
                elif d.get("keep"):
                    dec[x["id"]] = {"score": x.get("score") or 0.0, **mine}
                elif d.get("score") is None:
                    dec.pop(x["id"], None)
                else:
                    s = _num(d.get("score"))
                    if s is None or s < 0 or s > w + 1e-9:
                        raise Refusal(400, f"A score from 0 to {w:g}.")
                    dec[x["id"]] = {**{k2: v for k2, v in (dec.get(x["id"]) or {}).items() if k2 == "read"}, "score": round(s, 2), **mine}
                for k2 in ("score", "read", "rubric", "by", "at"):     # a blank decided: the question goes by its blanks again
                    qd0.pop(k2, None)
                if not qd0.get("blanks"):
                    qd0.pop("blanks", None)
            elif "read" in d:                     # what the answer says (typed, or the option picked): scored as the grader would
                from .autograde.grade import find_node, score_typed
                node = find_node(ex.exam, q.get("id"))
                if not node:
                    raise Refusal(409, "That question has changed in the exam since it was marked.")
                text = str(d.get("read") or "")[:200]
                s, shown = score_typed(node, text)
                one.setdefault("q", {}).setdefault(q["label"], {}).update(score=s, read=shown, by=g.user["name"], at=time.time())
            elif "score" in d and d.get("score") is None:     # undo: back to the grader's marking (a note stays)
                for k2 in ("score", "read", "blanks", "rubric", "by", "at"):
                    qd0.pop(k2, None)
            elif "score" in d:
                s = _num(d.get("score"))
                if s is None or s < 0 or s > (q.get("points") or 0) + 1e-9:
                    raise Refusal(400, f"A score from 0 to {q.get('points'):g}.")
                qd = one.setdefault("q", {}).setdefault(q["label"], {})
                qd.pop("read", None)
                qd.update(score=round(s, 2), by=g.user["name"], at=time.time())
            if not qd0:
                one["q"].pop(q["label"], None)
        ex.write_json("review.json", rv)
    _, roster = _roster(ex)
    return jsonify(booklet=next(x for x in view(ex, results, rv, roster) if x["key"] == k))


def _annotated(ex, results, shown, key, answers, templates, reader):
    """One booklet as its student gets it: PDF bytes (autograde/annotate.py)."""
    from .autograde import annotate
    b = next((x for x in results.get("booklets") or [] if _key(x) == key), None)
    me = next((x for x in shown if x["key"] == key), None)
    if not b or not me:
        raise Refusal(404, "That booklet isn't in the results any more: reload the page.")
    return annotate.booklet_pdf(ex.exam, templates, reader, b, me, answers=answers)


def _marked_against(ex):
    from .autograde import layout
    return [layout.load_template(p) for p in _templates(ex)[0]]


@scans_bp.get("/api/scans/annotated")
@team_api
def annotated():
    """A booklet with its marking drawn on, as the student would get it (to look at before it's emailed)."""
    ex = Exam(request.args, MARKERS)
    from .autograde import annotate
    results = ex.read_json("results.json", {})
    _, roster = _roster(ex)
    shown = view(ex, results, ex.read_json("review.json", {}), roster)
    key = str(request.args.get("booklet") or "")
    reader = annotate.page_reader(ex.path("uploads"))
    try:
        pdf = _annotated(ex, results, shown, key, request.args.get("answers") == "1", _marked_against(ex), reader)
    finally:
        reader.close()
    me = next(x for x in shown if x["key"] == key)
    name = re.sub(r"[^\w-]+", "-", f"{ex.e}-{me['student'].get('num') or 'booklet'}").strip("-")
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", download_name=f"{name}.pdf", as_attachment=request.args.get("download") == "1")


def _mail_job(ex, jobs, answers, by, cfg, reply, results, shown):
    """Each student their marked booklet, one email at a time, how far it's got in mail.json."""
    from . import mailer
    from .autograde import annotate
    st = ex.read_json("mail.json", {})
    st.update(state="running", started=time.time(), by=by, total=len(jobs), done=0, failed=[], answers=answers)
    st.setdefault("sent", {})
    ex.write_json("mail.json", st)
    reader = annotate.page_reader(ex.path("uploads"))
    try:
        templates = _marked_against(ex)
        for key, to, name, subject, body, fname in jobs:
            err = ""
            try:
                pdf = _annotated(ex, results, shown, key, answers, templates, reader)
                body.files = [(fname, pdf, "application/pdf")]
                err = mailer.deliver(to, subject, body, reply_to=reply, cfg=cfg)
            except Exception as x:              # one booklet that can't be drawn doesn't stop the rest
                err = str(x) or type(x).__name__
            if err and not (mailer.keep and err == "Email isn't set up."):
                st["failed"].append({"name": name, "why": err})
            else:
                st["sent"][key] = time.time()
            st["done"] += 1
            st["beat"] = time.time()
            ex.write_json("mail.json", st)
        st.update(state="done", finished=time.time())
    except Exception as x:
        st.update(state="failed", error=f"The emails stopped: {x}", finished=time.time())
    finally:
        reader.close()
    ex.write_json("mail.json", st)


@scans_bp.post("/api/scans/email")
@team_api
def email():
    """Email each finished booklet's student their booklet, marked (a PDF), in the background."""
    from . import classmail, mailer
    d = _args()
    ex = Exam(d, LEADS)
    results = ex.read_json("results.json", {})
    if not results:
        raise Refusal(409, "Mark the scans first.")
    book, roster = _roster(ex)
    who = {p["num"]: p for p in classmail.roster(book)["students"]}
    shown = view(ex, results, ex.read_json("review.json", {}), roster)
    only = set(d.get("booklets") or [])
    cfg, pf = classmail.settings_for(ex.owner, ex.o), classmail.prefs_for(ex.owner, ex.o)
    if not cfg.get("host") and not mailer.keep:
        raise Refusal(409, "Email isn't set up for this offering: set it up in the course's Email settings first.")
    head = classmail.head_for(ex.owner, ex.o)
    title = ex.settings.get("title") or ex.e
    code = head.get("code") or ex.o.split("/")[0].upper()
    jobs, waiting, missing = [], 0, []
    for b in shown:
        if only and b["key"] not in only:
            continue
        if not b["ready"]:
            waiting += 1
            continue
        p = who.get(b["student"]["num"])
        if not p:
            missing.append(b["student"].get("name") or b["student"]["num"])
            continue
        first = next((s.get("first") for s in roster if str(s.get("num")) == p["num"]), "") or ""
        msg = (f"{mailer.hi(first)}\n\nYour {title}, marked, is attached: your own pages, with each question's score and the "
               f"marker's comments. You got {b['total']:g} out of {b['out_of']:g}.\n")
        body = classmail.signed(pf, msg, head)
        fname = re.sub(r"[^\w-]+", "-", f"{code}-{title}-{p['num']}").strip("-") + ".pdf"
        jobs.append((b["key"], p["email"], p["name"], f"{code}: your marked {title}", body, fname))
    if not jobs:
        return jsonify(ok=True, emailing=0, waiting=waiting, missing=missing)
    key = ex.dir + "#mail"
    with _running_lock:
        if key in _threads and _threads[key].is_alive():
            raise Refusal(409, "They're being emailed already.")
        reply = pf["replyTo"] or g.user["email"]
        args = (ex, jobs, bool(d.get("answers")), g.user["name"], cfg, reply, results, shown)
        if mailer.keep:
            _mail_job(*args)
        else:
            t = threading.Thread(target=_mail_job, args=args, daemon=True, name="lectern-mail")
            _threads[key] = t
            t.start()
    return jsonify(ok=True, emailing=len(jobs), waiting=waiting, missing=missing, mail=ex.read_json("mail.json", {}))


@scans_bp.post("/api/scans/comment")
@team_api
def comment():
    """A new rubric comment, written while marking: saved into the exam (so it can be given again, and the marking guide
    has it) and given to this answer."""
    d = _args()
    ex = Exam(d, MARKERS)
    text = re.sub(r"\s+", " ", str(d.get("text") or "")).strip()[:300]
    delta = _num(d.get("delta"))
    if not text:
        raise Refusal(400, "Write the comment.")
    if delta is None:
        raise Refusal(400, "How many marks: -1, +2, or 0.")
    results = ex.read_json("results.json", {})
    b = next((x for x in results.get("booklets") or [] if _key(x) == str(d.get("booklet") or "")), None)
    q = b and next((x for x in b.get("questions") or [] if x["label"] == d.get("label")), None)
    if not q:
        raise Refusal(404, "That answer isn't in the results any more: reload the page.")
    path = f"{ex.o}/{ex.e}/exam.json"
    for _ in range(3):
        raw, sha = ex.repo.read_text(path)
        exam = json.loads(raw)
        from .autograde.grade import nodes_of
        node = (nodes_of(exam).get(q.get("id")) or (None,))[0]
        if not node:
            raise Refusal(409, "That question has changed in the exam since it was marked.")
        cid = secrets.token_hex(4)
        node.setdefault("rubric", []).append({"id": cid, "text": text, "delta": round(delta, 2)})
        if ex.repo.write_text(path, json.dumps(exam, indent=2, ensure_ascii=False) + "\n", sha, f"Rubric comment for {ex.e}", g.user["name"]):
            break
    else:
        raise Refusal(409, "The exam kept changing while the comment went in. Try again.")
    ex.exam = exam
    have = ((ex.read_json("review.json", {}).get("booklets") or {}).get(_key(b)) or {}).get("q", {}).get(q["label"], {}).get("rubric") or []
    return review_with(ex, {"booklet": _key(b), "label": q["label"], "rubric": [*have, cid]})


@scans_bp.post("/api/scans/send")
@team_api
def send():
    d = _args()
    ex = Exam(d, MARKERS)
    eid = ex.settings.get("link")
    results = ex.read_json("results.json", {})
    for _ in range(3):
        text, sha = ex.repo.read_text(f"{ex.o}/grades.json")
        if text is None:
            raise Refusal(404, "This offering has no gradebook.")
        book = json.loads(text)
        if not eid or not any(e.get("id") == eid for e in book.get("evals") or []):
            raise Refusal(409, "This exam isn't linked to an evaluation in the gradebook: open it from the evaluation's Build button.")
        roster = [s for s in book.get("students") or [] if not s.get("dropped")]
        bs = view(ex, results, ex.read_json("review.json", {}), roster)
        marks = book.setdefault("marks", {})
        sent, differ = 0, []
        for b in bs:
            if not b["ready"]:
                continue
            num = b["student"]["num"]
            cur = (marks.get(num) or {}).get(eid)
            if cur and cur.get("pts") is not None and abs((_num(cur.get("pts")) or 0) - b["total"]) > 1e-9 and not d.get("replace"):
                differ.append({"num": num, "name": b["student"].get("name", ""), "was": cur.get("pts"), "now": b["total"]})
                continue
            if not cur or cur.get("pts") != b["total"]:
                marks.setdefault(num, {})[eid] = {"pts": b["total"]}
                sent += 1
        if not sent:
            break
        if ex.repo.write_text(f"{ex.o}/grades.json", json.dumps(book, indent=2, ensure_ascii=False) + "\n", sha,
                              f"Marks for {eid} from scans", g.user["name"]):
            break
    else:
        raise Refusal(409, "The gradebook kept changing while the marks went in. Try again.")
    if sent:
        try:
            from . import accommodations
            accommodations._books.clear()
        except Exception:
            pass
        with _running_lock:
            rv = ex.read_json("review.json", {})
            rv["sent"] = {"at": time.time(), "by": g.user["name"], "n": sent}
            ex.write_json("review.json", rv)
    waiting = sum(1 for b in bs if not b["ready"])
    return jsonify(sent=sent, differ=differ, waiting=waiting)
