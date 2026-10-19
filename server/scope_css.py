"""Scope a tool's stylesheet to one element.

Every rule gets the tool's scope selector in front, so the three builders can
share one page without their styles touching each other or Lectern's own:

    .tb { … }                               →  [data-lt-tool="grades"] .tb { … }
    :root { --bg: … }                       →  [data-lt-tool="grades"] { --bg: … }
    :root:not([data-theme="light"]) .x {…}  →  [data-lt-tool="grades"]:not([data-theme="light"]) .x {…}
    body.dock-open .shell { … }             →  [data-lt-tool="grades"].dock-open .shell { … }

`html`, `body` and `:root` all become the scope element itself: inside Lectern
a tool's `document.body` and `document.documentElement` are that element too
(see static/js/scope.js). Rules inside @media / @supports are scoped the same
way; @keyframes and @font-face are left as they are.
"""
import re

_ROOTISH = re.compile(r'^(?::root|html|body)(?=$|[\s.:#\[>+~(])')
_ROOT_THEN_BODY = re.compile(r'^((?:[:.\[#](?:\([^)]*\)|\[[^\]]*\]|[^\s>+~(\[])*)*)\s+(?:html|body)(?=$|[\s.:#\[>+~(])')
_GROUPING =('@media', '@supports', '@container', '@layer', '@document')


def _strip_comments(css):
    out, i, n = [], 0, len(css)
    while i < n:
        c = css[i]
        if c in '"\'':
            j = _skip_string(css, i)
            out.append(css[i:j]); i = j
        elif css.startswith('/*', i):
            j = css.find('*/', i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c); i += 1
    return ''.join(out)


def _skip_string(css, i):
    q, j, n = css[i], i + 1, len(css)
    while j < n and css[j] != q:
        j += 2 if css[j] == '\\' else 1
    return min(j + 1, n)


def _match_brace(css, i):
    """css[i] is '{'; return the index just past its matching '}'."""
    depth, j, n = 0, i, len(css)
    while j < n:
        c = css[j]
        if c in '"\'':
            j = _skip_string(css, j); continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _find_top(css, i, chars):
    """The first of `chars` at or after i, outside strings, parentheses and brackets."""
    depth, j, n = 0, i, len(css)
    while j < n:
        c = css[j]
        if c in '"\'':
            j = _skip_string(css, j); continue
        if c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
        elif depth <= 0 and c in chars:
            return j
        j += 1
    return n


def split_selectors(sel):
    parts, i = [], 0
    while i <= len(sel):
        j = _find_top(sel, i, ',')
        parts.append(sel[i:j].strip())
        i = j + 1
    return [p for p in parts if p]


def scope_selector(sel, scope):
    m = _ROOTISH.match(sel)
    if m:
        rest = sel[m.end():]
        # ":root:not(…) body.on-settings": the body is the same element, so join them.
        b = _ROOT_THEN_BODY.match(rest)
        if b:
            rest = b.group(1) + rest[b.end():]
        return scope + rest
    return f'{scope} {sel}'


def _scope_block(css, scope):
    out, i, n = [], 0, len(css)
    while i < n:
        while i < n and css[i].isspace():
            i += 1
        if i >= n:
            break
        j = _find_top(css, i, '{;}')
        if j >= n:
            break
        head = css[i:j].strip()
        if css[j] in ';}':   # @import / @charset, or a stray token
            if head.startswith('@'):
                out.append(head + ';')
            i = j + 1
            continue
        end = _match_brace(css, j)
        body = css[j + 1:end - 1]
        if head.startswith('@'):
            name = head.split(None, 1)[0].lower()
            if name in _GROUPING:
                out.append(f'{head} {{\n{_scope_block(body, scope)}}}\n')
            else:
                out.append(f'{head} {{{body}}}\n')
        else:
            sels = ', '.join(scope_selector(s, scope) for s in split_selectors(head))
            out.append(f'{sels} {{{body}}}\n')
        i = end
    return ''.join(out)


def scope_css(css, scope):
    return _scope_block(_strip_comments(css), scope)
