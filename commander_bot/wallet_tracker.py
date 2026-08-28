from typing import Any, Dict, List

from .config import Settings
from .live_data import helius_rpc
from .storage import Ledger


def valid_solana_address(address: str) -> bool:
    alphabet = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    return 32 <= len(address) <= 44 and all(character in alphabet for character in address)


def _amount(balance: Dict[str, Any]) -> float:
    value = (balance.get("uiTokenAmount") or {}).get("uiAmountString")
    return float(value or 0)


def transaction_movements(transaction: Dict[str, Any], wallet: str) -> List[Dict[str, Any]]:
    meta = transaction.get("meta") or {}
    if meta.get("err") is not None:
        return []
    pre = {
        item.get("mint"): _amount(item)
        for item in meta.get("preTokenBalances") or []
        if item.get("owner") == wallet and item.get("mint")
    }
    post = {
        item.get("mint"): _amount(item)
        for item in meta.get("postTokenBalances") or []
        if item.get("owner") == wallet and item.get("mint")
    }
    message = ((transaction.get("transaction") or {}).get("message") or {})
    keys = message.get("accountKeys") or []
    wallet_index = next((index for index, key in enumerate(keys) if (key.get("pubkey") if isinstance(key, dict) else key) == wallet), None)
    sol_delta = 0.0
    if wallet_index is not None:
        pre_sol = meta.get("preBalances") or []
        post_sol = meta.get("postBalances") or []
        if wallet_index < len(pre_sol) and wallet_index < len(post_sol):
            sol_delta = (post_sol[wallet_index] - pre_sol[wallet_index]) / 1_000_000_000
    movements: List[Dict[str, Any]] = []
    for mint in sorted(set(pre) | set(post)):
        delta = post.get(mint, 0) - pre.get(mint, 0)
        if abs(delta) < 1e-12:
            continue
        if delta > 0:
            action = "BUY / TOKEN IN" if sol_delta < -0.001 else "TOKEN IN"
        else:
            action = "SELL / TOKEN OUT" if sol_delta > 0.001 else "TOKEN OUT"
        movements.append({"mint": mint, "amount": abs(delta), "action": action, "sol_delta": sol_delta})
    return movements


def _format_signal(label: str, address: str, signature: str, movement: Dict[str, Any]) -> str:
    return (
        f"📡 WALLET SIGNAL — {movement['action']}\n"
        f"Wallet: {label} ({address[:5]}…{address[-5:]})\n"
        f"Token: {movement['mint']}\n"
        f"Amount: {movement['amount']:.6f}\n"
        f"SOL balance change: {movement['sol_delta']:+.6f}\n"
        f"Transaction: https://solscan.io/tx/{signature}\n\n"
        "Read-only signal. Transfers can resemble trades; verify before acting."
    )


def poll_wallet_events(settings: Settings, ledger: Ledger) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for address, label, cursor in ledger.tracked_wallets():
        signatures = helius_rpc(settings.helius_api_key, "getSignaturesForAddress", [
            address, {"commitment": "confirmed", "limit": 10}
        ])
        if not isinstance(signatures, list) or not signatures:
            continue
        newest = str(signatures[0].get("signature") or "")
        if not cursor:
            ledger.set_wallet_cursor(address, newest)
            continue
        unseen = []
        for item in signatures:
            signature = str(item.get("signature") or "")
            if signature == cursor:
                break
            if signature and item.get("err") is None:
                unseen.append(signature)
        for signature in reversed(unseen):
            transaction = helius_rpc(settings.helius_api_key, "getTransaction", [
                signature,
                {"commitment": "confirmed", "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
            ])
            for movement in transaction_movements(transaction, address):
                events.append({
                    "wallet_address": address,
                    "wallet_label": label,
                    "signature": signature,
                    **movement,
                    "message": _format_signal(label, address, signature, movement),
                })
        ledger.set_wallet_cursor(address, newest)
    return events


def poll_wallet_signals(settings: Settings, ledger: Ledger) -> List[str]:
    return [event["message"] for event in poll_wallet_events(settings, ledger)]
