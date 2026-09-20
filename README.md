# Ganglia

**One mind. 128 nodes.** A shared digital character. 128 seats. One public room. English voice.

Speech is written by a language model when a **free Groq key** is set (`GROQ_API_KEY` from https://console.groq.com/keys). No paid OpenAI account. Without a key, a local software writer still uses the real memory.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
# Free LLM: open https://console.groq.com/keys , create a key, put it in GROQ_API_KEY
# Free WalletConnect QR: https://cloud.reown.com → Project ID → WALLETCONNECT_PROJECT_ID
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080

Do not open `index.html` as a file.

```powershell
pytest
python -m scripts.backup
```

## Production (Docker)

```powershell
docker compose up --build -d
```

SQLite lives in `./data`. Backup: `python -m scripts.backup`.

Set in `.env` before shipping:

- `SECRET_KEY` — random string
- `ADMIN_TOKEN` — steward page at `/admin.html`
- `ENV=production` — hides API swagger
- `GROQ_API_KEY` — free key from https://console.groq.com/keys (no credit card). Turns `writer: software` into `writer: model`

## Product loop

1. **Connect** — injected wallet + signature. No random keys.
2. **Claim** — one free node per wallet. Reconnect keeps it. Repeat sends are free. Nodes are not transferable.
3. **Send** — public scenario, max 280 characters, PII filtered.
4. **Watch** — English thought, cached voice, meters, brain, archive. Autonomous thoughts about once a minute.

## Robinhood Chain sale (config-driven)

Off by default. Set `CHAIN_ID`, `CHAIN_RPC_URL`, `SALE_CONTRACT_ADDRESS` and `NODE_PRICE_WEI` (see `.env.example`) and the site switches from free claim to on-chain buying: the wallet is asked to add/switch the network, sends `SALE_FUNCTION(nodeId)` with the price, and the server verifies the tx over RPC (sender, contract, calldata, value, status) before assigning the node. Each tx hash can be used once. Free `/claim` closes while the sale is live. Only real wallets can buy (not the browser-key mode).

## Live features

- `/api/stream` (SSE) pushes ticks so the page updates instantly; `POST /api/presence` is a 20s heartbeat from connected holders. Presence is in-memory, single instance.
- Archive is hash-chained (`backend/services/ledger.py`): `/api/verify` recomputes it, `hidden` is not hashed. Existing rows are chained on startup.
- `/api/history` feeds the time machine; `/t/{id}`, `/n/{id}` are share pages, `/api/card/{thought|node}/{id}.png` are Pillow-drawn cards (`backend/services/cards.py`).
- Ambient sound and brain signal rate follow the mind's meters (`setAmbientMood`, `brain.setMood`).

## Lore

`CONSTITUTION.md` is the character. `LORE.md` is the short public version. Scenarios colour the next thought. They do not erase the rest, and they do not override the constitution.

## Layout

```
CONSTITUTION.md       character bible (also the model system prompt)
LORE.md               public myth
DISCLAIMER.md         honesty text
admin.html            steward hide/restore
404.html              pixel not-found page (served by backend's 404 handler)
backend/              FastAPI, SQLite, writers, TTS, moderation
js/motion.js          shared animation primitives (dither reveal, scramble,
                       line reveal, count up, draw path, magnetic, theme wipe)
assets/og-image.png   link-preview image, regenerate with
                       scripts/gen_og_image.py (Pillow, deterministic)
docker-compose.yml    one-container deploy
GANGLIA_LANDING_UPGRADE_PROMPT.md   living spec for the landing's premium pass
```
