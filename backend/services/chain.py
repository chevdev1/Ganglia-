"""Robinhood Chain node sale: public config, calldata, and on-chain payment verification.

Contract-agnostic on purpose. Everything comes from settings; while chain_id,
sale_contract_address, chain_rpc_url and node_price_wei are unset the sale is
disabled and no purchase can be prepared or confirmed.
"""

from __future__ import annotations

import re

import httpx
from eth_utils import keccak, to_checksum_address

from backend.config import Settings

_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")


class ChainError(Exception):
    """A purchase could not be prepared or verified."""


def enabled(s: Settings) -> bool:
    """True only when the network, RPC, contract and price are all configured."""

    return bool(s.chain_id and s.chain_rpc_url and s.sale_contract_address and s.node_price_wei > 0)


def public_config(s: Settings) -> dict[str, object]:
    """Non-secret chain info the browser needs to add/switch the network."""

    return {
        "enabled": enabled(s),
        "chain_id": s.chain_id or None,
        "chain_name": s.chain_name,
        "explorer_url": s.chain_explorer_url or None,
        "currency_symbol": s.chain_currency_symbol,
        "currency_decimals": s.chain_currency_decimals,
        "rpc_url": s.chain_rpc_url or None,
        "sale_contract": s.sale_contract_address or None,
        "gngl_token": s.gngl_token_address or None,
        "price_wei": str(s.node_price_wei) if s.node_price_wei else None,
    }


def _calldata(s: Settings, node_id: int) -> str:
    selector = keccak(text=s.sale_function.replace(" ", ""))[:4].hex()
    return "0x" + selector + format(node_id, "064x")


def prepare(s: Settings, node_id: int) -> dict[str, object]:
    """Transaction the wallet should send to buy `node_id`."""

    if not enabled(s):
        raise ChainError("Node sale is not live yet.")
    if not 0 <= node_id <= 127:
        raise ChainError("Node does not exist.")
    return {
        "chain_id": s.chain_id,
        "to": to_checksum_address(s.sale_contract_address),
        "data": _calldata(s, node_id),
        "value": hex(s.node_price_wei),
    }


def _rpc(s: Settings, method: str, params: list[object]) -> object:
    try:
        res = httpx.post(
            s.chain_rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=15,
        )
        res.raise_for_status()
        body = res.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ChainError("Chain RPC is unreachable. Try again shortly.") from exc
    if body.get("error"):
        raise ChainError("Chain RPC rejected the request.")
    return body.get("result")


def verify(s: Settings, tx_hash: str, buyer: str, node_id: int) -> None:
    """Raise ChainError unless tx_hash is a confirmed, matching payment from `buyer`."""

    expected = prepare(s, node_id)
    if not _HASH.match(tx_hash):
        raise ChainError("Malformed transaction hash.")
    tx = _rpc(s, "eth_getTransactionByHash", [tx_hash])
    if not tx:
        raise ChainError("Transaction not found yet.")
    receipt = _rpc(s, "eth_getTransactionReceipt", [tx_hash])
    if not receipt:
        raise ChainError("Transaction is still pending.")
    if receipt.get("status") != "0x1":
        raise ChainError("Transaction failed on-chain.")
    if (tx.get("from") or "").lower() != buyer.lower():
        raise ChainError("Transaction was sent from a different wallet.")
    if (tx.get("to") or "").lower() != str(expected["to"]).lower():
        raise ChainError("Transaction did not go to the sale contract.")
    if (tx.get("input") or "").lower() != str(expected["data"]).lower():
        raise ChainError("Transaction is not a purchase of this node.")
    if int(tx.get("value") or "0x0", 16) < s.node_price_wei:
        raise ChainError("Payment is below the node price.")
