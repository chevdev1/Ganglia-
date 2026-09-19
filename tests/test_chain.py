"""Node-sale chain logic: disabled by default, calldata, and tx verification."""

import pytest

from backend.config import Settings
from backend.services import chain

CONTRACT = "0x" + "ab" * 20
BUYER = "0x" + "12" * 20
TX = "0x" + "cd" * 32


def cfg(**kw) -> Settings:
    base = dict(chain_id=1234, chain_rpc_url="http://rpc.invalid", sale_contract_address=CONTRACT, node_price_wei=10**15)
    base.update(kw)
    return Settings(_env_file=None, **base)


def test_disabled_by_default():
    s = Settings(_env_file=None)
    assert chain.enabled(s) is False
    assert chain.public_config(s)["enabled"] is False
    with pytest.raises(chain.ChainError):
        chain.prepare(s, 5)


def test_prepare_calldata_and_range():
    tx = chain.prepare(cfg(), 42)
    assert tx["to"].lower() == CONTRACT
    assert tx["data"].endswith(format(42, "064x")) and len(tx["data"]) == 2 + 8 + 64
    assert tx["value"] == hex(10**15)
    with pytest.raises(chain.ChainError):
        chain.prepare(cfg(), 128)


def _rpc_stub(monkeypatch, tx, receipt):
    def fake(_s, method, _p):
        return tx if method == "eth_getTransactionByHash" else receipt

    monkeypatch.setattr(chain, "_rpc", fake)


def good_tx(s):
    p = chain.prepare(s, 7)
    return {"from": BUYER, "to": p["to"], "input": p["data"], "value": p["value"]}


def test_verify_accepts_matching_payment(monkeypatch):
    s = cfg()
    _rpc_stub(monkeypatch, good_tx(s), {"status": "0x1"})
    chain.verify(s, TX, BUYER, 7)


@pytest.mark.parametrize(
    "mutate,receipt",
    [
        ({"from": "0x" + "99" * 20}, {"status": "0x1"}),
        ({"to": "0x" + "11" * 20}, {"status": "0x1"}),
        ({"input": "0xdeadbeef"}, {"status": "0x1"}),
        ({"value": hex(1)}, {"status": "0x1"}),
        ({}, {"status": "0x0"}),
        ({}, None),
    ],
)
def test_verify_rejects_bad_payment(monkeypatch, mutate, receipt):
    s = cfg()
    _rpc_stub(monkeypatch, {**good_tx(s), **mutate}, receipt)
    with pytest.raises(chain.ChainError):
        chain.verify(s, TX, BUYER, 7)


def test_verify_rejects_malformed_hash():
    with pytest.raises(chain.ChainError):
        chain.verify(cfg(), "0x123", BUYER, 7)


def _login(client):
    r = client.post("/api/auth/local", json={"secret": "0x" + "22" * 32})
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["address"]


def test_chain_endpoint_disabled_and_prepare_503(client):
    assert client.get("/api/chain").json()["enabled"] is False
    headers, _ = _login(client)
    assert client.post("/api/purchase/prepare", headers=headers, json={"node_id": 3}).status_code == 503
    assert client.post("/api/nodes/3/claim", headers=headers).status_code == 200


def test_full_purchase_flow_when_enabled(client, monkeypatch):
    from backend.main import settings

    for k, v in dict(chain_id=1234, chain_rpc_url="http://rpc.invalid", sale_contract_address=CONTRACT, node_price_wei=10**15).items():
        monkeypatch.setattr(settings, k, v)
    headers, address = _login(client)
    assert client.post("/api/nodes/3/claim", headers=headers).status_code == 402  # free claim closed
    prep = client.post("/api/purchase/prepare", headers=headers, json={"node_id": 3})
    assert prep.status_code == 200, prep.text
    tx = {"from": address, "to": prep.json()["to"], "input": prep.json()["data"], "value": prep.json()["value"]}
    monkeypatch.setattr(chain, "_rpc", lambda _s, m, _p: tx if m == "eth_getTransactionByHash" else {"status": "0x1"})
    ok = client.post("/api/purchase/confirm", headers=headers, json={"node_id": 3, "tx_hash": TX})
    assert ok.status_code == 200, ok.text
    assert ok.json()["node_id"] == 3
    replay = client.post("/api/purchase/confirm", headers=headers, json={"node_id": 3, "tx_hash": TX})
    assert replay.status_code == 409  # same payment can't be reused


def test_relics_only_from_real_data():
    from datetime import datetime, timedelta, timezone

    from backend.services.chamber import relics_for

    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    nodes = [(i, now - timedelta(days=100 - i), 0) for i in range(20)]  # 20 claimed, oldest first
    nodes.append((50, None, 99))  # unclaimed never gets relics
    nodes[0] = (0, nodes[0][1], 12)
    r = relics_for(nodes, now)
    assert r[0] == ["genesis", "long-standing", "voice"]
    assert "genesis" in r[15] and "genesis" not in r[16]
    assert 50 not in r


def test_state_exposes_relics_and_lore_page(client):
    r = client.post("/api/auth/local", json={"secret": "0x" + "33" * 32})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.post("/api/nodes/9/claim", headers=h).status_code == 200
    nodes = client.get("/api/state", headers=h).json()["nodes"]
    assert nodes[9]["relics"] == ["genesis"]
    assert nodes[10]["relics"] == []
    assert client.get("/lore.html").status_code == 200
