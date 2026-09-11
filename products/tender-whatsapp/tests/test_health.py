def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_home_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Tender" in r.text
