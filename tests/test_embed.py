"""A course page can be embedded in Quercus; Lectern's own pages can't be framed anywhere."""


def test_course_pages_embed_in_quercus(client):
    h = client.get("/c/nobody/csc108/f26/", base_url="https://localhost").headers
    assert "X-Frame-Options" not in h
    assert "frame-ancestors 'self' https://q.utoronto.ca https://*.instructure.com" in h["Content-Security-Policy"]


def test_lectern_itself_is_never_framed(client):
    h = client.get("/", base_url="https://localhost").headers
    assert h["X-Frame-Options"] == "DENY" and "frame-ancestors 'none'" in h["Content-Security-Policy"]
