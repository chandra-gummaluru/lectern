"""Writing the grader's results: results.json (everything), marks.csv (one row per booklet), review.html (each
booklet with pictures of every answer, the ones to look at first), and pictures/ (the JPEGs review.html shows)."""
import csv
import html
import json
import os

STATUS = {"auto": "Marked", "check": "Check", "manual": "Mark by hand", "missing": "Page missing"}
FOUND = {"auto": "Yes", "check": "Check", "missing": "Cover missing"}


def _fmt(x):
    if x is None:
        return ""
    return str(int(x)) if float(x) == int(x) else f"{x:g}"


def save_pictures(results, pics, prefix="pictures/"):
    """Each picture in the results (JPEG bytes) to a file in pics; the results then name it (prefix + file name)."""
    os.makedirs(pics, exist_ok=True)
    for i, b in enumerate(results["booklets"], 1):
        for key, item in [("student", b["student"])] + [(q["label"], q) for q in b["questions"]]:
            data = item.pop("picture", None)
            if data:
                name = f"b{i:03d}-{'cover' if key == 'student' else key.replace('(', '').replace(')', '')}.jpg"
                with open(os.path.join(pics, name), "wb") as f:
                    f.write(data)
                item["picture"] = prefix + name
    return results


def write(results, out_dir, title="Scanned exams"):
    save_pictures(results, os.path.join(out_dir, "pictures"))
    bs = results["booklets"]
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)

    labels = [q["label"] for q in bs[0]["questions"]] if bs else []
    with open(os.path.join(out_dir, "marks.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Booklet", "Scan pages", "Student number", "Name", "Student found", "Version", "Marked so far", "Out of", "To look at"] + labels)
        for i, b in enumerate(bs, 1):
            s = b["student"]
            w.writerow([i, "; ".join(b["pages"]), s.get("num", ""), s.get("name", ""), FOUND.get(s.get("status"), ""), b["version"],
                        _fmt(b["marked"]), _fmt(b["out_of"]), b["to_check"]] +
                       [_fmt(q["score"]) if q["status"] in ("auto", "check") else STATUS[q["status"]] for q in b["questions"]])

    e = html.escape
    img = lambda src, cls="": f'<img{" class=" + cls if cls else ""} src="{e(src)}" alt="">' if src else ""
    rows = []
    for i, b in enumerate(bs, 1):
        s = b["student"]
        who = f"{e(s.get('name') or 'Unknown student')} <span class=n>{e(s.get('num') or s.get('read') or '')}</span>"
        cands = "".join(f"<li>{e(c['num'])} {e(c['name'])}</li>" for c in s.get("candidates") or [])
        qrows = "".join(
            f"<tr class={q['status']}><th>{e(q['label'])}</th><td>{e(STATUS[q['status']])}</td>"
            f"<td class=num>{_fmt(q['score']) if q['score'] is not None else '–'} / {_fmt(q['points'])}</td>"
            f"<td>{e(str(q.get('read', '')))}</td><td>{e(str(q.get('answer', '')))}</td><td>{e(q.get('note', ''))}</td>"
            f"<td>{img(q.get('picture'))}</td></tr>"
            for q in b["questions"])
        rows.append(f"""<section id=b{i}><h2>Booklet {i}: {who}</h2>
<p class=meta>Student found: {e(FOUND.get(s.get('status'), ''))}{(' (' + e(s['note']) + ')') if s.get('note') else ''} · {_fmt(b['marked'])} of {_fmt(b['out_of'])} so far · {b['to_check']} to look at · {e('; '.join(b['pages']))}{(' · version ' + e(b['version'])) if b['version'] else ''}</p>
{img(s.get('picture'), 'cover')}{f'<p class=meta>Other possible students:</p><ul>{cands}</ul>' if s.get('status') == 'check' and cands else ''}
<table><tr><th>Question</th><th></th><th>Score</th><th>Read</th><th>Answer</th><th>Note</th><th>Scan</th></tr>{qrows}</table></section>""")
    unread = "".join(f"<li>{e(u['page'])}: {e(u['why'])}</li>" for u in results["unread"])
    toc = "".join(f"<li><a href=#b{i}>{i}. {e(b['student'].get('name') or b['student'].get('read') or 'Unknown')}</a> {('· ' + str(b['to_check']) + ' to look at') if b['to_check'] else ''}</li>" for i, b in enumerate(bs, 1))
    page = f"""<!doctype html><meta charset=utf-8><title>{e(title)}</title>
<style>
body{{font:14px/1.45 system-ui,sans-serif;margin:32px auto;max-width:1100px;color:#1f2329;padding:0 16px}}
h1{{font:600 28px Georgia,serif}} h2{{font:600 20px Georgia,serif;margin:32px 0 4px}} .n{{font:13px ui-monospace,monospace;color:#6b7280}}
.meta{{color:#4b5563;margin:2px 0 8px}} table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #e5e7eb;vertical-align:middle}}
td.num{{white-space:nowrap;font-variant-numeric:tabular-nums}} img{{max-height:90px;max-width:420px;border:1px solid #e5e7eb;border-radius:4px}} img.cover{{max-height:260px;max-width:100%}}
tr.check td:nth-child(2){{color:#a16207;font-weight:600}} tr.manual td:nth-child(2){{color:#1d4ed8;font-weight:600}} tr.missing td:nth-child(2){{color:#b91c1c;font-weight:600}}
ol{{columns:3}}
</style>
<h1>{e(title)}</h1><p class=meta>{len(bs)} booklets. "Check" means the grader marked it but a person should look; "Mark by hand" means it needs a person.</p>
<ol>{toc}</ol>{f'<h2>Pages that could not be placed</h2><ul>{unread}</ul>' if unread else ''}
{''.join(rows)}"""
    with open(os.path.join(out_dir, "review.html"), "w", encoding="utf-8") as f:
        f.write(page)
    return out_dir
