"""The three builders, served so they can share one page.

Each builder stays a single HTML file in tools/ (it still opens on its own).
For Lectern, the file is split into three parts, each kept to the tool's own
scope:

  /tools/<name>.css   its styles, every rule scoped to [data-lt-tool="<name>"]
  /tools/<name>.json  its body markup, plus the external stylesheets/scripts it loads
  /tools/<name>.js    its script, wrapped as Lectern.define("<name>", function (document, window, fetch) {…})
                      so `document` and `window` inside it are Lectern's scoped stand-ins

  /tools/<name>.html  the original file, to use the builder on its own

The split is cached and redone whenever the file changes.
"""
import base64
import hashlib
import json
import os
import re

from flask import Blueprint, Response, abort, send_file

from .paths import TOOLS_DIR
from .scope_css import scope_css

tools_bp = Blueprint('tools', __name__)

TOOLS = {
    'course': {'file': 'course-page-builder.html', 'title': 'Course page'},
    'grades': {'file': 'grade-builder.html', 'title': 'Grades'},
    'exams': {'file': 'exam-builder.html', 'title': 'Exams'},
}

_cache = {}

_BODY = re.compile(r'<body\b[^>]*>', re.I)
_MAIN_SCRIPT = re.compile(r'<script>', re.I)          # the tool's own script has no attributes
_STYLE = re.compile(r'<style\b[^>]*>(.*?)</style>', re.I | re.S)
_LINK_CSS = re.compile(r'<link\b(?=[^>]*\brel=["\']?stylesheet)[^>]*\bhref=["\']([^"\']+)["\'][^>]*>', re.I)
_SCRIPT_SRC = re.compile(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>\s*</script>', re.I)
_DROP = re.compile(r'<(?:title)\b[^>]*>.*?</title>|<link\b[^>]*>|<meta\b[^>]*>|<script\b[^>]*\bsrc=[^>]*>\s*</script>', re.I | re.S)


def scope_for(name):
    return f'[data-lt-tool="{name}"]'


def split_tool(html, name):
    """Split one builder's HTML into scoped CSS, body markup, script and external assets."""
    body = _BODY.search(html)
    if not body:
        raise ValueError(f'{name}: no <body>')
    m = _MAIN_SCRIPT.search(html, body.end())
    if not m:
        raise ValueError(f'{name}: no main <script> after <body>')
    end = html.find('</script>', m.end())
    if end < 0:
        raise ValueError(f'{name}: main <script> is never closed')
    before = html[:m.start()]            # <head> and the body markup: everything up to the script
    script = html[m.end():end]

    css = '\n'.join(_STYLE.findall(before))
    styles = _LINK_CSS.findall(before)
    scripts = _SCRIPT_SRC.findall(before)

    markup = _STYLE.sub('', before[body.end():])
    markup = _DROP.sub('', markup).strip()
    return {
        'css': scope_css(css, scope_for(name)),
        'markup': markup,
        'script': script,
        'styles': styles,
        'scripts': scripts,
    }


def _tool(name):
    if name not in TOOLS:
        abort(404)
    path = os.path.join(TOOLS_DIR, TOOLS[name]['file'])
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        abort(404)
    hit = _cache.get(name)
    if hit and hit[0] == mtime:
        return hit[1], path
    with open(path, encoding='utf-8') as f:
        parts = split_tool(f.read(), name)
    _cache[name] = (mtime, parts)
    return parts, path


@tools_bp.get('/tools/<name>.css')
def tool_css(name):
    parts, _ = _tool(name)
    return Response(parts['css'], mimetype='text/css')


@tools_bp.get('/tools/<name>.json')
def tool_meta(name):
    parts, _ = _tool(name)
    return Response(json.dumps({
        'name': name,
        'title': TOOLS[name]['title'],
        'markup': parts['markup'],
        'styles': parts['styles'],
        'scripts': parts['scripts'],
    }), mimetype='application/json')


@tools_bp.get('/tools/<name>.js')
def tool_js(name):
    parts, _ = _tool(name)
    # One line of wrapper on top, so line numbers in errors are the file's own minus the head.
    src = (f'Lectern.define({json.dumps(name)}, function (document, window, fetch) {{'
           f'{parts["script"]}\n}});\n//# sourceURL=lectern-tool-{name}.js\n')
    return Response(src, mimetype='application/javascript')


_INLINE = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.S)


@tools_bp.get('/tools/<name>.html')
def tool_html(name):
    """A builder on its own. It's one file with its script inline, so its policy allows exactly that script
    (by its hash) and nothing else inline."""
    from .core import csp
    _, path = _tool(name)
    with open(path, encoding='utf-8') as f:
        html = f.read()
    hashes = ["'sha256-%s'" % base64.b64encode(hashlib.sha256(m.group(1).encode('utf-8')).digest()).decode() for m in _INLINE.finditer(html)]
    resp = send_file(path, mimetype='text/html')
    resp.headers['Content-Security-Policy'] = csp(" ".join(hashes))
    return resp
