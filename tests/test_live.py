"""Hash-chained archive, history, presence, share pages and cards."""

from backend.db import session_factory
from backend.models import Output


def _login(client, secret="0x" + "44" * 32):
    r = client.post("/api/auth/local", json={"secret": secret})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _speak(client, headers, node=4, text="Remember this: rain on a tin roof."):
    assert client.post(f"/api/nodes/{node}/claim", headers=headers).status_code == 200
    assert client.post("/api/scenarios", headers=headers, json={"text": text}).status_code == 200


def test_chain_is_valid_and_thoughts_carry_hash(client):
    _speak(client, _login(client))
    v = client.get("/api/verify").json()
    assert v["ok"] is True and v["count"] >= 1 and len(v["head"]) == 64
    thoughts = client.get("/api/state").json()["thoughts"]
    assert all(t["hash"] and len(t["hash"]) == 12 for t in thoughts)


def test_tampering_breaks_the_chain(client):
    _speak(client, _login(client))
    with session_factory()() as s:
        row = s.query(Output).order_by(Output.id.asc()).first()
        row.text = "someone rewrote history"
        s.commit()
        first_id = row.id
    v = client.get("/api/verify").json()
    assert v["ok"] is False and v["broken_at"] == first_id


def test_hiding_a_thought_does_not_break_the_chain(client):
    _speak(client, _login(client))
    with session_factory()() as s:
        row = s.query(Output).order_by(Output.id.asc()).first()
        row.hidden = True
        s.commit()
    assert client.get("/api/verify").json()["ok"] is True


def test_history_is_oldest_first(client):
    _speak(client, _login(client))
    ids = [t["id"] for t in client.get("/api/history?limit=50").json()]
    assert ids == sorted(ids) and len(ids) >= 1


def test_presence_lights_only_holders(client):
    h = _login(client)
    assert client.post("/api/presence", headers=h).json()["present"] == []  # no node yet
    _speak(client, h, node=11)
    assert client.post("/api/presence", headers=h).json()["present"] == [11]
    state = client.get("/api/state").json()
    assert state["present"] == [11] and state["watching"] == 0
    assert client.post("/api/presence").status_code == 401


def test_share_pages_and_cards(client):
    _speak(client, _login(client), node=3)
    tid = client.get("/api/history").json()[-1]["id"]
    page = client.get(f"/t/{tid}")
    assert page.status_code == 200 and "og:image" in page.text and f"/api/card/thought/{tid}.png" in page.text
    assert client.get("/t/99999").status_code == 404
    node_page = client.get("/n/3")
    assert "Ganglia node 003" in node_page.text and "#node-003" in node_page.text
    for url in (f"/api/card/thought/{tid}.png", "/api/card/node/3.png", "/api/card/node/100.png"):
        r = client.get(url)
        assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get("/n/200").status_code == 404


def test_pulse_numbers_and_static_revalidation(client):
    h = _login(client)
    _speak(client, h, node=20)
    _speak_more = client.post("/api/scenarios", headers=h, json={"text": "A second memory, quiet and small."})
    p = client.get("/api/pulse").json()
    assert p["claimed"] == 1 and p["scenarios"] >= 1 and p["thoughts"] >= 1
    assert [r["region"] for r in p["regions"]][:2] == ["frontal", "parietal"] and len(p["regions"]) == 8
    assert p["regions"][1]["claimed"] == 1  # node 20 is parietal
    assert p["top"][0]["node_id"] == 20 and 0 <= p["model_share"] <= 100
    assert all({"curiosity", "intensity", "warmth"} <= set(m) for m in p["mood"])
    for path in ("/", "/docs.html", "/js/app.js", "/css/styles.css"):
        assert client.get(path).headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/api/health").headers or client.get("/api/health").headers["cache-control"] != "no-cache"
