"""End-to-end API tests: wallet login, claim persistence, memory, moderation."""

from __future__ import annotations

import time
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from fastapi.testclient import TestClient


def _wait_thoughts(client: TestClient, count: int, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Poll /api/state until at least `count` thoughts exist."""

    payload: dict[str, Any] = {}
    for _ in range(50):
        payload = client.get("/api/state", headers=headers).json()
        if len(payload["thoughts"]) >= count:
            return payload
        time.sleep(0.1)
    raise AssertionError(f"expected {count} thoughts, got {len(payload.get('thoughts', []))}")


def _connect(client: TestClient, account: LocalAccount | None = None) -> dict[str, str]:
    """Sign a nonce with a real Ethereum key and return auth headers."""

    wallet = account or Account.create()
    challenge = client.get("/api/auth/nonce", params={"address": wallet.address})
    assert challenge.status_code == 200, challenge.text
    body = challenge.json()
    signed = wallet.sign_message(encode_defunct(text=body["message"]))
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature
    response = client.post(
        "/api/auth/connect",
        json={"address": body["address"], "signature": signature},
    )
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    assert token
    assert response.json()["address"] == wallet.address.lower()
    return {"Authorization": f"Bearer {token}"}


def test_unsigned_connect_rejected(client: TestClient) -> None:
    """A raw address without a signature must not mint a session."""

    response = client.post("/api/auth/connect", json={"address": Account.create().address})
    assert response.status_code == 422


def test_index_html_serves_the_page(client: TestClient) -> None:
    """Browsers request /index.html; that must not 404 as JSON."""

    slash = client.get("/")
    named = client.get("/index.html")
    assert slash.status_code == 200
    assert named.status_code == 200
    assert "text/html" in named.headers.get("content-type", "")


def test_local_key_keeps_claimed_node(client: TestClient) -> None:
    """A browser key is a real wallet: same secret resumes the same node."""

    secret = "0x" + "11" * 32
    first = client.post("/api/auth/local", json={"secret": secret})
    assert first.status_code == 200, first.text
    address = first.json()["address"]
    headers = {"Authorization": f"Bearer {first.json()['token']}"}
    assert client.post("/api/nodes/5/claim", headers=headers).status_code == 200
    second = client.post("/api/auth/local", json={"secret": secret})
    assert second.status_code == 200
    assert second.json()["address"] == address
    resumed = client.get("/api/state", headers={"Authorization": f"Bearer {second.json()['token']}"}).json()
    assert resumed["me"]["node_id"] == 5
    bad = client.post("/api/auth/local", json={"secret": "0xzz"})
    assert bad.status_code == 422


def test_health_and_genesis(client: TestClient) -> None:
    """The mind boots with a genesis thought and a software signal."""

    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert health["signal"] == "software"
    assert health["wallet"] == "signature"
    state = _wait_thoughts(client, 1)
    assert state["thoughts"][0]["trigger"] == "autonomous"
    assert state["signal_source"] == "software"
    assert len(state["nodes"]) == 128


def test_claim_and_scenario_ground_memory(client: TestClient) -> None:
    """A claimed node can send a scenario that appears in the next thought."""

    headers = _connect(client)
    claimed = client.post("/api/nodes/7/claim", headers=headers)
    assert claimed.status_code == 200, claimed.text
    twice = client.post("/api/nodes/8/claim", headers=headers)
    assert twice.status_code == 409
    sent = client.post(
        "/api/scenarios",
        headers=headers,
        json={"text": "Remember this: my grandmother hummed while she cooked."},
    )
    assert sent.status_code == 200, sent.text
    state = _wait_thoughts(client, 3, headers)
    scenario_thoughts = [t for t in state["thoughts"] if t["trigger"] == "scenario"]
    assert scenario_thoughts
    blob = scenario_thoughts[0]["text"].lower() + " " + (scenario_thoughts[0]["scenario"] or "").lower()
    assert "grandmother" in blob
    assert state["me"]["node_id"] == 7


def test_reconnect_keeps_claimed_node(client: TestClient) -> None:
    """The same wallet keeps its node after a new signature."""

    wallet = Account.create()
    first = _connect(client, wallet)
    assert client.post("/api/nodes/9/claim", headers=first).status_code == 200
    second = _connect(client, wallet)
    state = client.get("/api/state", headers=second).json()
    assert state["me"]["node_id"] == 9


def test_second_user_cannot_steal_node(client: TestClient) -> None:
    """Two wallets cannot hold the same seat."""

    a = _connect(client)
    b = _connect(client)
    assert client.post("/api/nodes/3/claim", headers=a).status_code == 200
    assert client.post("/api/nodes/3/claim", headers=b).status_code == 409


def test_rejects_private_scenario(client: TestClient) -> None:
    """PII is blocked before it reaches memory."""

    headers = _connect(client)
    assert client.post("/api/nodes/1/claim", headers=headers).status_code == 200
    blocked = client.post(
        "/api/scenarios",
        headers=headers,
        json={"text": "email me at ada@example.com and I will tell you a secret"},
    )
    assert blocked.status_code == 400


def test_chamber_sigil_and_alias(client: TestClient) -> None:
    """The seat page returns a wallet sigil and keeps a standing name."""

    headers = _connect(client)
    door = client.get("/api/me/chamber", headers=headers)
    assert door.status_code == 200, door.text
    body = door.json()
    assert body["node_id"] is None
    assert body["title"] == "the doorway"
    assert len(body["sigil"]) == 8
    assert len(body["sigil"][0]) == 8
    named = client.post("/api/me/alias", headers=headers, json={"alias": "shore-walker"})
    assert named.status_code == 200, named.text
    assert named.json()["alias"] == "shore-walker"
    assert client.post("/api/nodes/11/claim", headers=headers).status_code == 200
    seated = client.get("/api/me/chamber", headers=headers).json()
    assert seated["node_id"] == 11
    assert seated["alias"] == "shore-walker"
    assert "shore-walker" in seated["standing_line"]
    assert seated["region"] == "frontal"
    assert len(seated["occupancy"]) == 128
    assert seated["occupancy"][11] is True
    assert seated["days_standing"] == 0
    cleared = client.post("/api/me/alias", headers=headers, json={"alias": ""})
    assert cleared.status_code == 200
    assert cleared.json()["alias"] is None


def test_steward_can_hide_a_thought(client: TestClient) -> None:
    """Hidden thoughts leave the public feed and stay available to admin."""

    headers = _connect(client)
    assert client.post("/api/nodes/4/claim", headers=headers).status_code == 200
    public = client.get("/api/state").json()
    thought_id = public["thoughts"][0]["id"]
    admin = {"X-Admin-Token": "test-admin"}
    overview = client.get("/api/admin/overview", headers=admin)
    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["nodes_total"] == 128
    assert body["thoughts_total"] >= 1
    assert "weather" in body
    hidden = client.post(
        f"/api/admin/thoughts/{thought_id}/hide",
        headers=admin,
        json={"hidden": True},
    )
    assert hidden.status_code == 200, hidden.text
    feed = client.get("/api/state").json()["thoughts"]
    assert all(row["id"] != thought_id for row in feed)
    listed = client.get("/api/admin/thoughts", headers=admin).json()
    assert any(row["id"] == thought_id and row["hidden"] for row in listed)
    only_hidden = client.get("/api/admin/thoughts", headers=admin, params={"visibility": "hidden"}).json()
    assert any(row["id"] == thought_id for row in only_hidden)
