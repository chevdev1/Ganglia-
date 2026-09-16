"""Wallet login: MetaMask (or any injected EOA) signs a one-time nonce. No random keys."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from eth_account.messages import encode_defunct
from eth_account import Account
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.models import LoginNonce, User

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
NONCE_TTL = timedelta(minutes=10)


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a bearer token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_address(address: str) -> str:
    """Require a real 20-byte hex address. Never mint a fake wallet."""

    candidate = (address or "").strip()
    if not ADDRESS_RE.match(candidate):
        raise HTTPException(400, "Connect a wallet. Address must be 0x plus 40 hex characters.")
    return candidate.lower()


def login_message(address: str, nonce: str) -> str:
    """Exact text MetaMask signs. Client and server must match."""

    return (
        "Ganglia — sign in to claim your node and send scenarios.\n\n"
        f"Address: {normalize_address(address)}\n"
        f"Nonce: {nonce}"
    )


def issue_nonce(session: Session, address: str) -> str:
    """Create a single-use nonce for this wallet."""

    addr = normalize_address(address)
    nonce = secrets.token_hex(16)
    session.add(LoginNonce(address=addr, nonce=nonce, created_at=datetime.now(timezone.utc)))
    session.flush()
    return nonce


def login_from_local_key(session: Session, secret: str) -> tuple[User, str]:
    """Sign the same nonce locally when this browser has no injected wallet.

    The key is a 32-byte hex secret kept in localStorage. Same secret, same
    address, same claimed node. This is a real secp256k1 wallet, not a random
    0x string minted on each click.
    """

    raw = (secret or "").strip()
    if raw.startswith("0x") or raw.startswith("0X"):
        raw = raw[2:]
    if len(raw) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in raw):
        raise HTTPException(400, "Bad browser key.")
    try:
        account = Account.from_key(bytes.fromhex(raw))
    except Exception as exc:
        raise HTTPException(400, "Bad browser key.") from exc
    nonce = issue_nonce(session, account.address)
    message = login_message(account.address, nonce)
    signed = account.sign_message(encode_defunct(text=message))
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature
    return verify_and_login(session, account.address, signature)


def verify_and_login(session: Session, address: str, signature: str) -> tuple[User, str]:
    """Recover the signer, consume the nonce, resume the same user row (and claimed node)."""

    addr = normalize_address(address)
    if not signature or not signature.startswith("0x"):
        raise HTTPException(400, "Missing wallet signature.")
    cutoff = datetime.now(timezone.utc) - NONCE_TTL
    row = session.scalar(
        select(LoginNonce)
        .where(LoginNonce.address == addr, LoginNonce.created_at >= cutoff)
        .order_by(LoginNonce.id.desc())
    )
    if row is None:
        raise HTTPException(401, "Nonce expired. Connect again.")
    message = login_message(addr, row.nonce)
    try:
        recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception as exc:
        session.delete(row)
        session.flush()
        raise HTTPException(401, "Could not read that signature.") from exc
    session.delete(row)
    session.flush()
    if recovered.lower() != addr:
        raise HTTPException(401, "Signature does not match this wallet.")
    return issue_user(session, addr)


def get_user_by_token(session: Session, token: str) -> User | None:
    """Look up a user from the raw bearer token."""

    return session.scalar(select(User).where(User.token_hash == hash_token(token)))


def issue_user(session: Session, address: str) -> tuple[User, str]:
    """Find or create the wallet's user. Same address always keeps the same node."""

    addr = normalize_address(address)
    user = session.scalar(select(User).where(User.address == addr))
    token = secrets.token_urlsafe(32)
    if user is None:
        user = User(address=addr, token_hash=hash_token(token))
        session.add(user)
        session.flush()
    else:
        user.token_hash = hash_token(token)
        session.flush()
    return user, token


def clear_token(session: Session, user: User) -> None:
    """Invalidate the current browser session. Ownership of the node stays."""

    user.token_hash = hash_token("revoked:" + secrets.token_urlsafe(16))
    session.flush()


def current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """Require a valid bearer token."""

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Connect wallet first.")
    token = authorization.split(" ", 1)[1].strip()
    user = get_user_by_token(session, token)
    if user is None:
        raise HTTPException(401, "Session expired. Connect wallet again.")
    return user


def optional_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User | None:
    """Return the caller if a token is present and valid."""

    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return get_user_by_token(session, token)
