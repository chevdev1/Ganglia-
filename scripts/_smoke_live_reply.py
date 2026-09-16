"""Smoke: send one scenario and print the writer + reply (no secrets)."""

from __future__ import annotations

import asyncio
import sys

import httpx
from eth_account import Account

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8098"


async def main() -> None:
    secret = Account.create().key.hex()
    async with httpx.AsyncClient(timeout=180.0) as client:
        boot = (await client.get(f"{BASE}/api/state")).json()
        print("boot", boot.get("writer"), boot.get("model_ready"))
        login = await client.post(f"{BASE}/api/auth/local", json={"secret": secret})
        login.raise_for_status()
        token = login.json()["token"]
        headers = {"Authorization": "Bearer " + token}
        state = (await client.get(f"{BASE}/api/state", headers=headers)).json()
        free = next(n["id"] for n in state["nodes"] if n["owner"] is None)
        (await client.post(f"{BASE}/api/nodes/{free}/claim", headers=headers)).raise_for_status()
        sent = await client.post(
            f"{BASE}/api/scenarios",
            headers=headers,
            json={"text": "Who are you when nobody is watching the room?"},
        )
        print("scenario", sent.status_code, sent.text)
        sent.raise_for_status()
        await asyncio.sleep(2)
        thoughts = (await client.get(f"{BASE}/api/state", headers=headers)).json()["thoughts"]
        for t in thoughts[:3]:
            if t.get("trigger") == "scenario":
                print("WRITER", t.get("writer"))
                print("TEXT", (t.get("text") or "")[:400])
                break


asyncio.run(main())
