"""Ganglia HTTP API and static site."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth import (
    clear_token,
    current_user,
    issue_nonce,
    login_from_local_key,
    login_message,
    normalize_address,
    optional_user,
    verify_and_login,
)
from backend.config import ROOT, get_settings
from backend.db import get_session, init_engine, session_factory
from backend.models import Node, Output, Purchase, Scenario, User
from backend.schemas import (
    AdminOverviewOut,
    AliasIn,
    ChamberOut,
    CharacterStateOut,
    ClaimOut,
    ConnectIn,
    LocalKeyIn,
    MeOut,
    NodeOut,
    NonceOut,
    ScenarioIn,
    StateOut,
    ThoughtOut,
    TraceOut,
)
from backend.services.chamber import (
    REGION_MYTH,
    clean_alias,
    cooldown_left,
    days_standing,
    occupancy_map,
    seat_title,
    standing_line,
    traces_for,
    wallet_sigil,
)
from backend.services.memory import (
    ensure_world,
    load_thoughts,
    region_for,
    serialize_thought,
    short_address,
)
from backend.services import chain
from backend.services.mind import MindRuntime, claim_node, seed_genesis
from backend.services.moderation import moderate_scenario

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ganglia")

settings = get_settings()
mind = MindRuntime(settings)
(ROOT / "data" / "voices").mkdir(parents=True, exist_ok=True)
_PRODUCTION = settings.env.lower() == "production"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Open the database, seed genesis, start the mind worker."""

    init_engine()
    factory = session_factory()
    with factory() as session:
        seed_genesis(session, mind)
        session.commit()
    mind.start()
    yield
    await mind.stop()


app = FastAPI(
    title="Ganglia",
    docs_url=None if _PRODUCTION else "/api/docs",
    redoc_url=None,
    openapi_url=None if _PRODUCTION else "/api/openapi.json",
    lifespan=lifespan,
)
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]
MaybeUser = Annotated[User | None, Depends(optional_user)]


@app.exception_handler(StarletteHTTPException)
async def _custom_404(request: Request, exc: StarletteHTTPException):
    """Pixel 404 page for missing pages/assets. API 404s stay JSON."""

    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        return FileResponse(ROOT / "404.html", status_code=404)
    return await http_exception_handler(request, exc)


def _me_out(user: User | None, token: str | None = None) -> MeOut | None:
    """Public identity block."""

    if user is None:
        return None
    return MeOut(address=user.address, node_id=user.node_id, token=token, alias=user.alias)


def _nodes(session: Session) -> list[NodeOut]:
    """128-node map for the grid."""

    nodes = session.scalars(select(Node).order_by(Node.id)).all()
    owners = {user.id: user for user in session.scalars(select(User)).all()}
    return [
        NodeOut(
            id=node.id,
            owner=short_address(owners[node.owner_id].address) if node.owner_id else None,
            alias=owners[node.owner_id].alias if node.owner_id else None,
            scenarios=node.scenario_count,
            region=region_for(node.id),
        )
        for node in nodes
    ]


@app.get("/api/health")
def health() -> dict[str, object]:
    """Liveness plus which writer is active."""

    return {
        "ok": True,
        "writer": mind.writer_name,
        "signal": "software",
        "busy": mind.busy,
        "tts": settings.tts_enabled,
        "env": settings.env,
        "model_ready": bool(settings.openai_api_key.strip()),
        "wallet": "signature",
        "walletconnect": bool(settings.walletconnect_project_id.strip()),
        "wc_project_id": settings.walletconnect_project_id.strip() or None,
    }


@app.get("/api/auth/nonce", response_model=NonceOut)
def nonce(address: str, session: SessionDep) -> NonceOut:
    """Issue a one-time message for the wallet to sign."""

    value = issue_nonce(session, address)
    addr = normalize_address(address)
    return NonceOut(address=addr, nonce=value, message=login_message(addr, value))


@app.post("/api/auth/connect", response_model=MeOut)
def connect(body: ConnectIn, session: SessionDep) -> MeOut:
    """Verify personal_sign and resume this wallet's claimed node."""

    user, token = verify_and_login(session, body.address, body.signature)
    return MeOut(address=user.address, node_id=user.node_id, token=token, alias=user.alias)


@app.post("/api/auth/local", response_model=MeOut)
def connect_local(body: LocalKeyIn, session: SessionDep) -> MeOut:
    """Resume a browser key when MetaMask is not injected (Cursor preview, etc.)."""

    user, token = login_from_local_key(session, body.secret)
    return MeOut(address=user.address, node_id=user.node_id, token=token, alias=user.alias)


@app.post("/api/auth/logout")
def logout(user: UserDep, session: SessionDep) -> dict[str, bool]:
    """Drop the browser session. The claimed node stays on the wallet."""

    clear_token(session, user)
    return {"ok": True}


@app.get("/api/me", response_model=MeOut)
def me(user: UserDep) -> MeOut:
    """Return the connected identity."""

    return MeOut(address=user.address, node_id=user.node_id, alias=user.alias)


@app.get("/api/me/chamber", response_model=ChamberOut)
def chamber(session: SessionDep, user: UserDep) -> ChamberOut:
    """Personal seat: sigil, traces, cooldown, standing myth."""

    memory = ensure_world(session)
    node = session.get(Node, user.node_id) if user.node_id is not None else None
    region = region_for(user.node_id) if user.node_id is not None else None
    myth, blurb = REGION_MYTH[region] if region else ("the doorway", "Claim a free node to step out of the doorway.")
    now = datetime.now(timezone.utc)
    traces = [
        TraceOut(
            id=row.id,
            trigger=row.trigger_type,
            scenario=row.scenario.raw_text if row.scenario is not None else None,
            text=row.text,
            created_at=row.created_at,
            curiosity=row.curiosity,
            intensity=row.intensity,
            warmth=row.warmth,
            voice_url=row.voice_path or None,
        )
        for row in traces_for(session, user)
    ]
    occupied = occupancy_map(session)
    claimed_at = node.claimed_at if node else None
    return ChamberOut(
        address=user.address,
        alias=user.alias,
        node_id=user.node_id,
        region=region,
        title=seat_title(user.node_id),
        blurb=blurb,
        standing_line=standing_line(user.node_id, claimed_at, user.alias),
        claimed_at=claimed_at,
        days_standing=days_standing(claimed_at, now),
        scenario_count=node.scenario_count if node else 0,
        cooldown_seconds=cooldown_left(user, settings, now),
        sigil=wallet_sigil(user.address),
        traces=traces,
        occupancy=occupied,
        occupied_count=sum(occupied),
        cycle=memory.cycle,
        summary=memory.summary_text or "",
        weather=CharacterStateOut(
            curiosity=memory.curiosity,
            intensity=memory.intensity,
            warmth=memory.warmth,
            focus=memory.focus,
            restlessness=memory.restlessness,
            unresolved_thought=memory.unresolved_thought or "",
        ),
        model_ready=bool(settings.openai_api_key.strip()),
        writer=mind.writer_name,
    )


@app.post("/api/me/alias", response_model=MeOut)
def set_alias(body: AliasIn, session: SessionDep, user: UserDep) -> MeOut:
    """Set a public standing name. Wallet stays the source of ownership."""

    try:
        alias = clean_alias(body.alias)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if alias is not None:
        taken = session.scalar(select(User).where(User.alias == alias, User.id != user.id))
        if taken is not None:
            raise HTTPException(409, "That standing name is already taken.")
    user.alias = alias
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "That standing name is already taken.") from exc
    return MeOut(address=user.address, node_id=user.node_id, alias=user.alias)


@app.get("/api/state", response_model=StateOut)
def state(session: SessionDep, user: MaybeUser) -> StateOut:
    """Bootstrap the landing page from the shared database."""

    memory = ensure_world(session)
    thoughts = [serialize_thought(row) for row in load_thoughts(session)]
    return StateOut(
        me=_me_out(user),
        nodes=_nodes(session),
        thoughts=thoughts,
        state=CharacterStateOut(
            curiosity=memory.curiosity,
            intensity=memory.intensity,
            warmth=memory.warmth,
            focus=memory.focus,
            restlessness=memory.restlessness,
            unresolved_thought=memory.unresolved_thought or "",
        ),
        cycle=memory.cycle,
        busy=mind.busy,
        status=mind.phase,
        signal_source="software",
        writer=mind.writer_name,
        summary=memory.summary_text,
        model_ready=bool(settings.openai_api_key.strip()),
    )


@app.get("/api/thoughts", response_model=list[ThoughtOut])
def thoughts(session: SessionDep, after_id: int = Query(default=0, ge=0)) -> list[ThoughtOut]:
    """Poll for new archive entries."""

    rows = load_thoughts(session, after_id=after_id)
    if after_id:
        return [serialize_thought(row) for row in rows]
    return [serialize_thought(row) for row in rows]


@app.post("/api/nodes/{node_id}/claim", response_model=ClaimOut)
async def claim(node_id: int, session: SessionDep, user: UserDep) -> ClaimOut:
    """Take a free node. Repeat scenarios from it do not require another claim."""

    if chain.enabled(settings):
        raise HTTPException(402, "Nodes are sold on-chain now. Use Buy.")
    try:
        node = claim_node(session, user, node_id)
        session.commit()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Already claimed.") from exc
    await mind.process({"type": "claim", "node_id": node.id, "phase": "writing"})
    return ClaimOut(node_id=node.id, address=user.address)


class PurchaseIn(BaseModel):
    """Which node the caller wants to buy, and (on confirm) the payment tx."""

    node_id: int
    tx_hash: str | None = None


@app.get("/api/chain")
def chain_info() -> dict[str, object]:
    """Public Robinhood Chain sale config. enabled=false until contracts are configured."""

    return chain.public_config(settings)


@app.post("/api/purchase/prepare")
def purchase_prepare(body: PurchaseIn, session: SessionDep, user: UserDep) -> dict[str, object]:
    """Transaction the wallet should send to buy a free node."""

    node = session.get(Node, body.node_id)
    if node is not None and node.owner_id is not None:
        raise HTTPException(409, "Already claimed.")
    if user.node_id is not None:
        raise HTTPException(409, "You already hold a node.")
    try:
        return chain.prepare(settings, body.node_id)
    except chain.ChainError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/purchase/confirm", response_model=ClaimOut)
async def purchase_confirm(body: PurchaseIn, session: SessionDep, user: UserDep) -> ClaimOut:
    """Verify the payment on-chain, then give the caller the node."""

    if not body.tx_hash:
        raise HTTPException(422, "tx_hash is required.")
    tx_hash = body.tx_hash.lower()
    if session.scalar(select(Purchase).where(Purchase.tx_hash == tx_hash)):
        raise HTTPException(409, "This payment was already used.")
    try:
        await asyncio.to_thread(chain.verify, settings, tx_hash, user.address, body.node_id)
    except chain.ChainError as exc:
        raise HTTPException(402, str(exc)) from exc
    try:
        node = claim_node(session, user, body.node_id)
        session.add(Purchase(tx_hash=tx_hash, address=user.address, node_id=node.id, chain_id=settings.chain_id))
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(409, f"{exc} Your payment is on-chain; contact the steward with tx {tx_hash}.") from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Already claimed.") from exc
    await mind.process({"type": "claim", "node_id": node.id, "phase": "writing"})
    return ClaimOut(node_id=node.id, address=user.address)


@app.post("/api/scenarios", response_model=dict[str, int])
async def send_scenario(body: ScenarioIn, session: SessionDep, user: UserDep) -> dict[str, int]:
    """Publish a scenario from the caller's node into shared memory."""

    if user.node_id is None:
        raise HTTPException(403, "Claim a node to send scenarios.")
    if not settings.openai_api_key.strip() and not settings.allow_software_writer:
        raise HTTPException(
            503,
            "The mind is offline. Add OPENAI_API_KEY to .env and restart the server.",
        )
    verdict = moderate_scenario(body.text, settings.max_scenario_len)
    if not verdict.ok:
        raise HTTPException(400, verdict.reason)
    now = datetime.now(timezone.utc)
    if user.last_scenario_at is not None:
        last = user.last_scenario_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        wait = settings.scenario_cooldown_seconds - (now - last).total_seconds()
        if wait > 0:
            raise HTTPException(429, f"Wait {int(wait)}s before sending another scenario.")
    node = session.get(Node, user.node_id)
    if node is None:
        raise HTTPException(409, "Your node is missing.")
    scenario = Scenario(
        node_id=user.node_id,
        author_id=user.id,
        raw_text=body.text.strip(),
        moderation_status="approved",
        created_at=now,
    )
    session.add(scenario)
    user.last_scenario_at = now
    node.scenario_count += 1
    session.flush()
    scenario_id = scenario.id
    session.commit()
    await mind.process({"type": "scenario", "scenario_id": scenario_id, "phase": "reading your scenario"})
    return {"id": scenario_id}


class HideIn(BaseModel):
    """Steward action: hide or restore a public thought."""

    hidden: bool = True


def require_admin(x_admin_token: str | None = Header(default=None)) -> str:
    """Gate steward routes on ADMIN_TOKEN."""

    expected = settings.admin_token.strip()
    if not expected or not x_admin_token or x_admin_token != expected:
        raise HTTPException(401, "Admin only.")
    return expected


@app.get("/api/admin/overview", response_model=AdminOverviewOut)
def admin_overview(session: SessionDep, _: str = Depends(require_admin)) -> AdminOverviewOut:
    """Ops snapshot: seats, archive, memory weather, writer health."""

    memory = ensure_world(session)
    nodes = list(session.scalars(select(Node).order_by(Node.id.asc())).all())
    claimed = sum(1 for node in nodes if node.owner_id is not None)
    thoughts_total = session.scalar(select(func.count()).select_from(Output)) or 0
    thoughts_hidden = session.scalar(select(func.count()).select_from(Output).where(Output.hidden.is_(True))) or 0
    scenarios = session.scalar(select(func.count()).select_from(Scenario)) or 0
    users = session.scalar(select(func.count()).select_from(User)) or 0
    recent = list(
        session.scalars(select(Scenario).order_by(Scenario.id.desc()).limit(8)).all()
    )
    return AdminOverviewOut(
        cycle=memory.cycle,
        writer=mind.writer_name,
        model_ready=bool(settings.openai_api_key.strip()),
        signal_source="software",
        busy=mind.busy,
        status=mind.phase,
        nodes_total=len(nodes) or 128,
        nodes_claimed=claimed,
        nodes_free=(len(nodes) or 128) - claimed,
        users=users,
        scenarios=scenarios,
        thoughts_total=thoughts_total,
        thoughts_public=thoughts_total - thoughts_hidden,
        thoughts_hidden=thoughts_hidden,
        summary=memory.summary_text or "",
        weather=CharacterStateOut(
            curiosity=memory.curiosity,
            intensity=memory.intensity,
            warmth=memory.warmth,
            focus=memory.focus,
            restlessness=memory.restlessness,
            unresolved_thought=memory.unresolved_thought or "",
        ),
        unresolved_thought=memory.unresolved_thought or "",
        recent_scenarios=[row.raw_text for row in reversed(recent)],
        occupancy=[node.owner_id is not None for node in nodes],
    )


@app.get("/api/admin/thoughts", response_model=list[ThoughtOut])
def admin_thoughts(
    session: SessionDep,
    _: str = Depends(require_admin),
    q: str = Query(default=""),
    visibility: str = Query(default="all"),
) -> list[ThoughtOut]:
    """Newest thoughts including hidden ones. Optional filter + search."""

    rows = load_thoughts(session, include_hidden=True, limit=120)
    needle = q.strip().lower()
    out: list[ThoughtOut] = []
    for row in rows:
        if visibility == "hidden" and not row.hidden:
            continue
        if visibility == "public" and row.hidden:
            continue
        card = serialize_thought(row)
        if needle:
            blob = " ".join(
                [
                    card.text or "",
                    card.scenario or "",
                    card.trigger or "",
                    str(card.node_id if card.node_id is not None else ""),
                ]
            ).lower()
            if needle not in blob:
                continue
        out.append(card)
    return out


@app.post("/api/admin/thoughts/{thought_id}/hide", response_model=ThoughtOut)
def admin_hide(
    thought_id: int, body: HideIn, session: SessionDep, _: str = Depends(require_admin)
) -> ThoughtOut:
    """Hide a thought from the public archive without deleting memory."""

    row = session.get(Output, thought_id)
    if row is None:
        raise HTTPException(404, "Thought not found.")
    row.hidden = body.hidden
    session.flush()
    log.info("thought %s hidden=%s", thought_id, body.hidden)
    return serialize_thought(row)


@app.get("/")
def index() -> FileResponse:
    """Landing page."""

    return FileResponse(ROOT / "index.html")


@app.get("/index.html")
def index_file() -> FileResponse:
    """Same landing page. Browsers often request /index.html instead of /."""

    return FileResponse(ROOT / "index.html")


@app.get("/docs.html")
def docs_page() -> FileResponse:
    """Human documentation. API swagger lives at /api/docs."""

    return FileResponse(ROOT / "docs.html")


@app.get("/me.html")
def chamber_page() -> FileResponse:
    """Personal seat / cabinet."""

    return FileResponse(ROOT / "me.html")


@app.get("/admin.html")
def admin_page() -> FileResponse:
    """Steward console. Requires ADMIN_TOKEN in the page, not a public nav link."""

    return FileResponse(ROOT / "admin.html")


app.mount("/css", StaticFiles(directory=str(ROOT / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(ROOT / "js")), name="js")
app.mount("/assets", StaticFiles(directory=str(ROOT / "assets")), name="assets")
app.mount("/data/voices", StaticFiles(directory=str(Path(ROOT / "data" / "voices"))), name="voices")
