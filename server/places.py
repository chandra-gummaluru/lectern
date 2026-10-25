"""Places: finding a building or address for an activity's or office hours' Where (static/js/place.js).

  GET /api/places?q=Bahen Centre     signed in: up to 6 places, [{ name, address, lat, lon }]

It asks a geocoder: OpenStreetMap's Nominatim by default (https://nominatim.openstreetmap.org/search), or the
one in LECTERN_GEOCODER_URL (any Nominatim-compatible search); LECTERN_GEOCODER=off turns it off (the Where
fields then take the place's name as typed). Nominatim's use policy: a User-Agent that says who's asking, at
most one request a second, and answers kept: so this server asks at most once a second (in this process), and
remembers answers for a day. The browser never talks to the geocoder itself (the pages' CSP keeps it here).
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

from flask import Blueprint, jsonify, request

from .auth import Refusal, limiter, signed_in

places_bp = Blueprint("places", __name__)

DEFAULT_URL = "https://nominatim.openstreetmap.org/search"
CACHE_SECONDS = 24 * 3600
MAX_CACHE = 2000
_cache = {}                 # query → (time, results)
_lock = threading.Lock()
_last = [0.0]               # when the geocoder was last asked


def enabled():
    return os.environ.get("LECTERN_GEOCODER", "").strip().lower() not in ("off", "0", "no", "false")


def _ask(q):
    """The geocoder's answer for q, as places (it's asked at most once a second)."""
    url = os.environ.get("LECTERN_GEOCODER_URL", "").strip() or DEFAULT_URL
    with _lock:
        wait = _last[0] + 1.0 - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
    qs = urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 6, "addressdetails": 0})
    req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": "Lectern course pages (lectern; places search)", "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=6) as r:
        raw = json.loads(r.read().decode("utf-8"))
    out = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        full = str(x.get("display_name") or "")
        name = str(x.get("name") or "").strip() or full.split(",")[0].strip()
        rest = full[len(name):].lstrip(", ").strip() if full.startswith(name) else full
        try:
            lat, lon = round(float(x.get("lat")), 6), round(float(x.get("lon")), 6)
        except (TypeError, ValueError):
            continue
        out.append({"name": name[:200], "address": rest[:300], "lat": lat, "lon": lon})
    return out


def search(q):
    key = " ".join(q.lower().split())
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    res = _ask(q)
    with _lock:
        if len(_cache) >= MAX_CACHE:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[: MAX_CACHE // 4]:
                del _cache[k]
        _cache[key] = (now, res)
    return res


@places_bp.get("/api/places")
@signed_in
def places():
    from flask import g
    q = " ".join(str(request.args.get("q") or "").split())[:120]
    if len(q) < 3:
        return jsonify(places=[])
    if not enabled():
        return jsonify(places=[], off=True)
    if not limiter.ok(f"places:{g.user['id']}", 30, 60):
        raise Refusal(429, "Too many searches; wait a moment.")
    try:
        return jsonify(places=search(q))
    except Exception:
        return jsonify(places=[], error="The place search isn't answering right now. Type the place's name instead."), 200
