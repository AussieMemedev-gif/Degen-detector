import json
import sqlite3
from dataclasses import asdict
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
