import asyncio
import httpx
from eth_account import Account

BASE = "http://127.0.0.1:8094"
acct = Account.create()
secret = acct.key.hex()


async def main() -> None:
    async with httpx.AsyncClient(timeout=120.0) as client:
        state = await client.get(f"{BASE}/api/state")
        boot = state.json()
        print("boot", boot["writer"], boot["model_ready"], "focus" in boot["state"])

        login = await client.post(f"{BASE}/api/auth/local", json={"secret": secret})
        print("login", login.status_code)
        login.raise_for_status()
        token = login.json()["token"]
        headers = {"Authorization": "Bearer " + token}

        state = await client.get(f"{BASE}/api/state", headers=headers)
        free = next(node["id"] for node in state.json()["nodes"] if node["owner"] is None)
        claim = await client.post(f"{BASE}/api/nodes/{free}/claim", headers=headers)
        print("claim", claim.status_code)
        claim.raise_for_status()

        sent = await client.post(
            f"{BASE}/api/scenarios",
            headers=headers,
            json={"text": "Why do harbours keep returning in quiet rooms?"},
        )
        print("scenario", sent.status_code, sent.text)
        sent.raise_for_status()

        await asyncio.sleep(3)
        data = (await client.get(f"{BASE}/api/state", headers=headers)).json()
        print("writer", data["writer"], "cycle", data["cycle"])
        print("state", data["state"])
        for thought in data["thoughts"][:4]:
            print("---", thought["trigger"], thought["writer"])
            print(thought["text"][:300])
            if thought.get("scenario"):
                print("scn:", thought["scenario"][:100])


asyncio.run(main())
