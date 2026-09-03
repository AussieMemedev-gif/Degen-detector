import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .models import CommanderDecision, TokenSnapshot


class Ledger:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
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
        self.connection.execute("""CREATE TABLE IF NOT EXISTS practice_account (
            id INTEGER PRIMARY KEY CHECK(id = 1), cash_usd REAL NOT NULL,
            starting_balance_usd REAL NOT NULL, created_at TEXT NOT NULL)""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS practice_positions (
            mint TEXT PRIMARY KEY, symbol TEXT NOT NULL, token_quantity REAL NOT NULL,
            average_entry_price REAL NOT NULL, cost_basis_usd REAL NOT NULL,
            opened_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS practice_trades (
            id INTEGER PRIMARY KEY, occurred_at TEXT NOT NULL, mint TEXT NOT NULL,
            symbol TEXT NOT NULL, side TEXT NOT NULL, token_quantity REAL NOT NULL,
            fill_price_usd REAL NOT NULL, gross_usd REAL NOT NULL, fee_usd REAL NOT NULL,
            realized_pnl_usd REAL NOT NULL DEFAULT 0, sol_size REAL NOT NULL DEFAULT 0)""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS master_trade_decisions (
            id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL, mint TEXT NOT NULL,
            symbol TEXT NOT NULL, action TEXT NOT NULL, verdict TEXT NOT NULL,
            commander_score REAL NOT NULL, data_confidence REAL NOT NULL,
            reasons_json TEXT NOT NULL)""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS master_paper_positions (
            id INTEGER PRIMARY KEY, mint TEXT NOT NULL, symbol TEXT NOT NULL,
            opened_at TEXT NOT NULL, closed_at TEXT NOT NULL DEFAULT '',
            entry_price REAL NOT NULL, current_price REAL NOT NULL,
            high_price REAL NOT NULL, quantity REAL NOT NULL, position_usd REAL NOT NULL,
            stop_price REAL NOT NULL, target_one REAL NOT NULL, target_two REAL NOT NULL,
            trailing_stop_pct REAL NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN',
            exit_reason TEXT NOT NULL DEFAULT '', realized_pnl_usd REAL NOT NULL DEFAULT 0)""")
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

    def record_master_decision(
        self, observed_at: datetime, mint: str, symbol: str, action: str,
        verdict: str, commander_score: float, data_confidence: float, reasons: list[str],
    ) -> None:
        self.connection.execute(
            "INSERT INTO master_trade_decisions(observed_at,mint,symbol,action,verdict,"
            "commander_score,data_confidence,reasons_json) VALUES(?,?,?,?,?,?,?,?)",
            (observed_at.astimezone(timezone.utc).isoformat(), mint, symbol, action, verdict,
             commander_score, data_confidence, json.dumps(reasons)),
        )
        self.connection.commit()

    def recent_master_decisions(self, limit: int = 10) -> list[tuple]:
        return self.connection.execute(
            "SELECT observed_at,symbol,action,verdict,commander_score,data_confidence,reasons_json "
            "FROM master_trade_decisions ORDER BY id DESC LIMIT ?", (limit,),
        ).fetchall()

    def open_master_position(
        self, token: TokenSnapshot, position_usd: float, stop_price: float,
        target_one: float, target_two: float, trailing_stop_pct: float,
    ) -> bool:
        if token.price_usd <= 0 or position_usd <= 0:
            return False
        exists = self.connection.execute(
            "SELECT id FROM master_paper_positions WHERE mint=? AND status='OPEN'", (token.mint,)
        ).fetchone()
        if exists:
            return False
        self.connection.execute(
            "INSERT INTO master_paper_positions(mint,symbol,opened_at,entry_price,current_price,"
            "high_price,quantity,position_usd,stop_price,target_one,target_two,trailing_stop_pct) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (token.mint, token.symbol, token.observed_at.astimezone(timezone.utc).isoformat(),
             token.price_usd, token.price_usd, token.price_usd, position_usd / token.price_usd,
             position_usd, stop_price, target_one, target_two, trailing_stop_pct),
        )
        self.connection.commit()
        return True

    def master_open_positions(self) -> list[tuple]:
        return self.connection.execute(
            "SELECT id,mint,symbol,opened_at,entry_price,current_price,high_price,quantity,"
            "position_usd,stop_price,target_one,target_two,trailing_stop_pct "
            "FROM master_paper_positions WHERE status='OPEN' ORDER BY opened_at"
        ).fetchall()

    def mark_master_price(self, position_id: int, price: float) -> None:
        self.connection.execute(
            "UPDATE master_paper_positions SET current_price=?,high_price=MAX(high_price,?) WHERE id=?",
            (price, price, position_id),
        )
        self.connection.commit()

    def close_master_position(
        self, position_id: int, exit_price: float, reason: str, closed_at: datetime,
    ) -> float:
        row = self.connection.execute(
            "SELECT quantity,position_usd FROM master_paper_positions WHERE id=? AND status='OPEN'",
            (position_id,),
        ).fetchone()
        if not row:
            return 0.0
        pnl = float(row[0]) * exit_price - float(row[1])
        self.connection.execute(
            "UPDATE master_paper_positions SET current_price=?,closed_at=?,status='CLOSED',"
            "exit_reason=?,realized_pnl_usd=? WHERE id=?",
            (exit_price, closed_at.astimezone(timezone.utc).isoformat(), reason, pnl, position_id),
        )
        self.connection.commit()
        return pnl

    def master_performance(self) -> dict:
        closed = self.connection.execute(
            "SELECT position_usd,realized_pnl_usd FROM master_paper_positions WHERE status='CLOSED'"
        ).fetchall()
        open_count = int(self.connection.execute(
            "SELECT COUNT(*) FROM master_paper_positions WHERE status='OPEN'"
        ).fetchone()[0])
        pnl = sum(float(row[1]) for row in closed)
        wins = sum(1 for row in closed if float(row[1]) > 0)
        losses = [float(row[1]) for row in closed if float(row[1]) <= 0]
        gains = [float(row[1]) for row in closed if float(row[1]) > 0]
        return {
            "closed": len(closed), "open": open_count, "wins": wins, "pnl": pnl,
            "win_rate": wins / len(closed) * 100 if closed else 0.0,
            "average_win": sum(gains) / len(gains) if gains else 0.0,
            "average_loss": sum(losses) / len(losses) if losses else 0.0,
        }

    def master_realized_pnl_since(self, since: datetime) -> float:
        rows = self.connection.execute(
            "SELECT realized_pnl_usd FROM master_paper_positions "
            "WHERE status='CLOSED' AND closed_at>=?",
            (since.astimezone(timezone.utc).isoformat(),),
        ).fetchall()
        return sum(float(row[0]) for row in rows)

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

    def ensure_practice_account(self, starting_balance_usd: float) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO practice_account(id,cash_usd,starting_balance_usd,created_at) "
            "VALUES(1,?,?,?)",
            (starting_balance_usd, starting_balance_usd, datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def practice_cash(self) -> float:
        row = self.connection.execute("SELECT cash_usd FROM practice_account WHERE id=1").fetchone()
        return float(row[0]) if row else 0.0

    def practice_account(self) -> tuple | None:
        return self.connection.execute(
            "SELECT cash_usd,starting_balance_usd,created_at FROM practice_account WHERE id=1"
        ).fetchone()

    def practice_trade_counts(self) -> tuple[int, int, int]:
        row = self.connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(CASE WHEN side='BUY' THEN 1 ELSE 0 END),0),"
            "COALESCE(SUM(CASE WHEN side='SELL' THEN 1 ELSE 0 END),0) FROM practice_trades"
        ).fetchone()
        return int(row[0]), int(row[1]), int(row[2])

    def practice_positions(self) -> list[tuple]:
        return self.connection.execute(
            "SELECT mint,symbol,token_quantity,average_entry_price,cost_basis_usd,opened_at,updated_at "
            "FROM practice_positions ORDER BY updated_at DESC"
        ).fetchall()

    def practice_position(self, mint: str) -> tuple | None:
        return self.connection.execute(
            "SELECT mint,symbol,token_quantity,average_entry_price,cost_basis_usd,opened_at,updated_at "
            "FROM practice_positions WHERE mint=?", (mint,)
        ).fetchone()

    def practice_hourly_buys(self, now: datetime) -> float:
        since = now.astimezone(timezone.utc) - timedelta(hours=1)
        row = self.connection.execute(
            "SELECT COALESCE(SUM(gross_usd + fee_usd),0) FROM practice_trades "
            "WHERE side='BUY' AND occurred_at>=?", (since.isoformat(),)
        ).fetchone()
        return float(row[0] or 0)

    def practice_buy(
        self, mint: str, symbol: str, quantity: float, fill_price_usd: float,
        gross_usd: float, fee_usd: float, sol_size: float, now: datetime,
    ) -> None:
        existing = self.practice_position(mint)
        timestamp = now.astimezone(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                "UPDATE practice_account SET cash_usd=cash_usd-? WHERE id=1",
                (gross_usd + fee_usd,),
            )
            if existing:
                new_quantity = float(existing[2]) + quantity
                new_cost = float(existing[4]) + gross_usd + fee_usd
                self.connection.execute(
                    "UPDATE practice_positions SET symbol=?,token_quantity=?,average_entry_price=?,"
                    "cost_basis_usd=?,updated_at=? WHERE mint=?",
                    (symbol, new_quantity, new_cost / new_quantity, new_cost, timestamp, mint),
                )
            else:
                total_cost = gross_usd + fee_usd
                self.connection.execute(
                    "INSERT INTO practice_positions(mint,symbol,token_quantity,average_entry_price,"
                    "cost_basis_usd,opened_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (mint, symbol, quantity, total_cost / quantity, total_cost, timestamp, timestamp),
                )
            self.connection.execute(
                "INSERT INTO practice_trades(occurred_at,mint,symbol,side,token_quantity,fill_price_usd,"
                "gross_usd,fee_usd,realized_pnl_usd,sol_size) VALUES(?,?,?,?,?,?,?,?,0,?)",
                (timestamp, mint, symbol, "BUY", quantity, fill_price_usd, gross_usd, fee_usd, sol_size),
            )

    def practice_sell(
        self, mint: str, symbol: str, quantity: float, fill_price_usd: float,
        gross_usd: float, fee_usd: float, realized_pnl_usd: float, now: datetime,
    ) -> None:
        existing = self.practice_position(mint)
        if not existing:
            raise ValueError("practice position not found")
        timestamp = now.astimezone(timezone.utc).isoformat()
        remaining = max(0.0, float(existing[2]) - quantity)
        remaining_cost = max(0.0, float(existing[4]) - float(existing[3]) * quantity)
        with self.connection:
            self.connection.execute(
                "UPDATE practice_account SET cash_usd=cash_usd+? WHERE id=1", (gross_usd - fee_usd,)
            )
            if remaining <= 1e-12:
                self.connection.execute("DELETE FROM practice_positions WHERE mint=?", (mint,))
            else:
                self.connection.execute(
                    "UPDATE practice_positions SET token_quantity=?,cost_basis_usd=?,updated_at=? WHERE mint=?",
                    (remaining, remaining_cost, timestamp, mint),
                )
            self.connection.execute(
                "INSERT INTO practice_trades(occurred_at,mint,symbol,side,token_quantity,fill_price_usd,"
                "gross_usd,fee_usd,realized_pnl_usd,sol_size) VALUES(?,?,?,?,?,?,?,?,?,0)",
                (timestamp, mint, symbol, "SELL", quantity, fill_price_usd, gross_usd, fee_usd, realized_pnl_usd),
            )

    def practice_history(self, limit: int = 20) -> list[tuple]:
        return self.connection.execute(
            "SELECT occurred_at,symbol,mint,side,token_quantity,fill_price_usd,gross_usd,fee_usd,"
            "realized_pnl_usd,sol_size FROM practice_trades ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def practice_statistics(self) -> tuple[int, int, float, float]:
        row = self.connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(CASE WHEN realized_pnl_usd>0 THEN 1 ELSE 0 END),0),"
            "COALESCE(SUM(realized_pnl_usd),0),COALESCE(SUM(fee_usd),0) "
            "FROM practice_trades WHERE side='SELL'"
        ).fetchone()
        return int(row[0]), int(row[1]), float(row[2]), float(row[3])

    def practice_top_gains(self, limit: int = 10) -> list[tuple]:
        return self.connection.execute(
            "SELECT occurred_at,symbol,mint,realized_pnl_usd,gross_usd FROM practice_trades "
            "WHERE side='SELL' AND realized_pnl_usd>0 ORDER BY realized_pnl_usd DESC LIMIT ?", (limit,)
        ).fetchall()
