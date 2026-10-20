"""Lectern acting as its GitHub App (not as a signed-in person), for accommodation requests.

A student asking for an accommodation isn't signed in to anything, so the server reads the
course's gradebook and records the request with the app's own access to the repository the
instructor installed it on. That access comes from the app's private key:

  LECTERN_GH_PRIVATE_KEY_FILE  path to the .pem file GitHub gives you ("Generate a private key"
                               on the app's page). *.pem is in .gitignore.
  LECTERN_GH_APP_ID            the app's ID (optional: the Client ID works too)

The app signs a short-lived JWT with the key, swaps it for an installation token for one
repository (an hour), and uses that like any GitHub token.

Every call to GitHub goes through `request()`, which tests replace.
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def configured():
    return bool(_key_path() and _issuer())


def _key_path():
    return os.environ.get("LECTERN_GH_PRIVATE_KEY_FILE", "")


def _issuer():
    return os.environ.get("LECTERN_GH_APP_ID") or os.environ.get("LECTERN_GH_CLIENT_ID", "")


def request(method, path, token, body=None, auth="token"):
    """One GitHub API call → (status, parsed JSON or None). Never raises for HTTP errors."""
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Lectern",
        **({"Authorization": f"{'Bearer' if auth == 'bearer' else 'token'} {token}"} if token else {}),
        **({"Content-Type": "application/json"} if data is not None else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except Exception:
            return e.code, None
    except Exception as e:   # network
        return 599, {"message": f"Couldn't reach GitHub ({e.__class__.__name__})."}


def _app_jwt():
    import jwt   # PyJWT[crypto]; only needed once accommodations are set up
    with open(_key_path(), "rb") as f:
        key = f.read()
    now = int(time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": _issuer()}, key, algorithm="RS256")


_tokens = {}            # "owner/repo" → (token, expires at)
_lock = threading.Lock()


def installation_token(full):
    """A token for one repository, as the app. Cached until a few minutes before it expires."""
    with _lock:
        hit = _tokens.get(full.lower())
        if hit and hit[1] > time.time() + 300:
            return hit[0]
    if not configured():
        raise GitHubError(503, "Accommodation requests aren't set up on this server yet.")
    app = _app_jwt()
    st, inst = request("GET", f"/repos/{full}/installation", app, auth="bearer")
    if st != 200:
        raise GitHubError(404 if st == 404 else 502, "Lectern can't reach this course's repository.")
    st, tok = request("POST", f"/app/installations/{inst['id']}/access_tokens", app,
                      {"repositories": [full.split("/", 1)[1]]}, auth="bearer")
    if st != 201:
        raise GitHubError(502, "Lectern couldn't get access to this course's repository.")
    with _lock:
        _tokens[full.lower()] = (tok["token"], time.time() + 3300)
    return tok["token"]


def _contents(full, path):
    return f"/repos/{full}/contents/{urllib.parse.quote(path)}"


def read_file(full, path, token):
    """(text, sha), or (None, None) when the file isn't there."""
    st, d = request("GET", _contents(full, path), token)
    if st == 404:
        return None, None
    if st != 200 or not isinstance(d, dict) or "content" not in d:
        raise GitHubError(502 if st != 401 and st != 403 else st, (d or {}).get("message") or "Couldn't read from GitHub.")
    return base64.b64decode(d["content"]).decode("utf-8"), d.get("sha")


def write_file(full, path, text, sha, message, token):
    """Create or update a file. Returns True, or False if it changed since `sha` was read."""
    body = {"message": message, "content": base64.b64encode(text.encode("utf-8")).decode()}
    if sha:
        body["sha"] = sha
    st, d = request("PUT", _contents(full, path), token, body)
    if st in (200, 201):
        return True
    if st == 409 or (st == 422 and sha is None):   # changed (or made) by someone else in the meantime
        return False
    raise GitHubError(st if st in (401, 403, 404) else 502, (d or {}).get("message") or "Couldn't save to GitHub.")


def can_push(full, user_token):
    """Whether the signed-in person (their own token) may change this repository."""
    st, d = request("GET", f"/repos/{full}", user_token)
    return st == 200 and bool(((d or {}).get("permissions") or {}).get("push"))
