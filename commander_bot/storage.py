import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from .models import CommanderDecision, TokenSnapshot


class Ledger:
    def __init__(self, path: str):
        self.connection = sqlite3.connect(path)
        self.connection.execute("""CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL, mint TEXT NOT NULL,
            symbol TEXT NOT NULL, score REAL NOT NULL, status TEXT NOT NULL,
            snapshot_json TEXT NOT NULL, decision_json TEXT NOT NULL)""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS alert_history (
            mint TEXT PRIMARY KEY, alerted_at TEXT NOT NULL)""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS tracked_wallets (
            address TEXT PRIMARY KEY, label TEXT NOT NULL, created_at TEXT NOT NULL,
            last_signature TEXT NOT NULL DEFAULT '')""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS paper_positions (
            id INTEGER PRIMARY KEY, wallet_address TEXT NOT NULL, wallet_label TEXT NOT NULL,
            mint TEXT NOT NULL, opened_at TEXT NOT NULL, entry_price REAL NOT NULL,
            token_quantity REAL NOT NULL, position_usd REAL NOT NULL,
            entry_signature TEXT NOT NULL, closed_at TEXT NOT NULL DEFAULT '',
            exit_price REAL NOT NULL DEFAULT 0, exit_signature TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'OPEN', realized_pnl_usd REAL NOT NULL DEFAULT 0)""")
        self.connection.commit()

    def record(self, token: TokenSnapshot, decision: CommanderDecision) -> None:
        snapshot = asdict(token)
        snapshot["observed_at"] = token.observed_at.isoformat()
        payload = asdict(decision)
        self.connection.execute(
            "INSERT INTO decisions(observed_at,mint,symbol,score,status,snapshot_json,decision_json) VALUES(?,?,?,?,?,?,?)",
            (token.observed_at.isoformat(), token.mint, token.symbol, decision.score, decision.status, json.dumps(snapshot), json.dumps(payload)),
        )
        self.connection.commit()

    def get_state(self, key: str, default: str = "") -> str:
        row = self.connection.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    def set_state(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO bot_state(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.connection.commit()

    def recently_alerted(self, mint: str, cooldown_minutes: int, now: datetime) -> bool:
        row = self.connection.execute(
            "SELECT alerted_at FROM alert_history WHERE mint = ?", (mint,)
        ).fetchone()
        if not row:
            return False
        alerted_at = datetime.fromisoformat(row[0])
        return alerted_at > now.astimezone(timezone.utc) - timedelta(minutes=cooldown_minutes)

    def record_alert(self, mint: str, now: datetime) -> None:
        self.connection.execute(
            "INSERT INTO alert_history(mint,alerted_at) VALUES(?,?) "
            "ON CONFLICT(mint) DO UPDATE SET alerted_at=excluded.alerted_at",
            (mint, now.astimezone(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def add_tracked_wallet(self, address: str, label: str) -> None:
        self.connection.execute(
            "INSERT INTO tracked_wallets(address,label,created_at,last_signature) VALUES(?,?,?, '') "
            "ON CONFLICT(address) DO UPDATE SET label=excluded.label",
            (address, label, datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def remove_tracked_wallet(self, address: str) -> bool:
        cursor = self.connection.execute("DELETE FROM tracked_wallets WHERE address = ?", (address,))
        self.connection.commit()
        return cursor.rowcount > 0

    def tracked_wallets(self) -> list[tuple[str, str, str]]:
        return self.connection.execute(
            "SELECT address,label,last_signature FROM tracked_wallets ORDER BY created_at"
        ).fetchall()

    def set_wallet_cursor(self, address: str, signature: str) -> None:
        self.connection.execute(
            "UPDATE tracked_wallets SET last_signature = ? WHERE address = ?",
            (signature, address),
        )
        self.connection.commit()

    def open_paper_position(
        self, wallet_address: str, wallet_label: str, mint: str, entry_price: float,
        position_usd: float, signature: str, opened_at: datetime,
    ) -> bool:
        existing = self.connection.execute(
            "SELECT id FROM paper_positions WHERE wallet_address = ? AND mint = ? AND status = 'OPEN'",
            (wallet_address, mint),
        ).fetchone()
        if existing or entry_price <= 0 or position_usd <= 0:
            return False
        self.connection.execute(
            "INSERT INTO paper_positions(wallet_address,wallet_label,mint,opened_at,entry_price,"
            "token_quantity,position_usd,entry_signature) VALUES(?,?,?,?,?,?,?,?)",
            (wallet_address, wallet_label, mint, opened_at.astimezone(timezone.utc).isoformat(),
             entry_price, position_usd / entry_price, position_usd, signature),
        )
        self.connection.commit()
        return True

    def close_paper_positions(
        self, wallet_address: str, mint: str, exit_price: float, signature: str, closed_at: datetime,
    ) -> list[float]:
        rows = self.connection.execute(
            "SELECT id,token_quantity,position_usd FROM paper_positions "
            "WHERE wallet_address = ? AND mint = ? AND status = 'OPEN'",
            (wallet_address, mint),
        ).fetchall()
        results: list[float] = []
        for position_id, quantity, position_usd in rows:
            pnl = (float(quantity) * exit_price) - float(position_usd)
            self.connection.execute(
                "UPDATE paper_positions SET closed_at=?,exit_price=?,exit_signature=?,status='CLOSED',"
                "realized_pnl_usd=? WHERE id=?",
                (closed_at.astimezone(timezone.utc).isoformat(), exit_price, signature, pnl, position_id),
            )
            results.append(pnl)
        self.connection.commit()
        return results

    def open_paper_positions(self) -> list[tuple]:
        return self.connection.execute(
            "SELECT wallet_label,mint,opened_at,entry_price,token_quantity,position_usd "
            "FROM paper_positions WHERE status='OPEN' ORDER BY opened_at DESC"
        ).fetchall()

    def paper_totals(self) -> tuple[int, float, int, int]:
        row = self.connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(realized_pnl_usd),0),"
            "COALESCE(SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END),0),"
            "COALESCE(SUM(CASE WHEN realized_pnl_usd <= 0 THEN 1 ELSE 0 END),0) "
            "FROM paper_positions WHERE status='CLOSED'"
        ).fetchone()
        return int(row[0]), float(row[1]), int(row[2]), int(row[3])

    def trader_performance(self) -> list[tuple]:
        return self.connection.execute(
            "SELECT wallet_label,wallet_address,COUNT(*),"
            "SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END),"
            "COALESCE(SUM(realized_pnl_usd),0) FROM paper_positions "
            "WHERE status='CLOSED' GROUP BY wallet_address,wallet_label "
            "ORDER BY COALESCE(SUM(realized_pnl_usd),0) DESC"
        ).fetchall()
