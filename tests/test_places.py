"""Places (server/places.py): the Where fields' search goes through the server, which asks the geocoder."""
import json

import pytest

from server import places


class FakeResp:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def geo(monkeypatch):
    asked = []

    def urlopen(req, timeout=0):
        asked.append(req.full_url)
        return FakeResp([{"name": "Bahen Centre for Information Technology", "display_name": "Bahen Centre for Information Technology, 40, St George Street, Toronto",
                          "lat": "43.6596", "lon": "-79.3972"}, {"display_name": "No coordinates"}])
    monkeypatch.setattr(places.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(places, "_cache", {})
    monkeypatch.setattr(places, "_last", [0.0])
    return asked


def test_a_search_finds_places_and_remembers_them(geo):
    r = places.search("Bahen Centre")
    assert r == [{"name": "Bahen Centre for Information Technology", "address": "40, St George Street, Toronto", "lat": 43.6596, "lon": -79.3972}]
    assert places.search("  bahen   centre ") == r and len(geo) == 1      # the same search, from memory
    assert "q=Bahen+Centre" in geo[0] and "nominatim" in geo[0]


def test_it_can_be_turned_off(monkeypatch, geo):
    monkeypatch.setenv("LECTERN_GEOCODER", "off")
    assert not places.enabled()
