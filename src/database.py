import sqlite3
import os
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trades.db")
MAX_SCANS = 1000


class Database:
    def __init__(self):
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    price REAL,
                    rsi REAL,
                    ema_cross TEXT,
                    macd_hist REAL,
                    vol_ratio REAL,
                    haber_sentiment REAL,
                    action TEXT,
                    confidence REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    system_log TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price REAL,
                    qty REAL,
                    pnl REAL,
                    reason TEXT,
                    entry_price REAL,
                    mode TEXT DEFAULT 'SIM'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price REAL,
                    confidence REAL,
                    notified_to TEXT DEFAULT 'telegram'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    strategy_action TEXT,
                    strategy_score REAL,
                    strategy_reason TEXT,
                    ai_prob REAL,
                    ai_veto INTEGER DEFAULT 0,
                    final_action TEXT,
                    final_reason TEXT,
                    price REAL,
                    executed INTEGER DEFAULT 0
                )
            """)
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN mode TEXT DEFAULT 'SIM'")
            except:
                pass
            conn.commit()
        finally:
            conn.close()

    def save_scan(self, price, rsi, ema_cross, macd_hist, vol_ratio, haber_sentiment, action, confidence, stop_loss=0, take_profit=0, system_log=""):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO scans (created_at, price, rsi, ema_cross, macd_hist, vol_ratio, haber_sentiment, action, confidence, stop_loss, take_profit, system_log) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(), price, rsi, ema_cross, macd_hist, vol_ratio, haber_sentiment, action, confidence, stop_loss, take_profit, system_log)
            )
            count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
            if count > MAX_SCANS:
                conn.execute(f"DELETE FROM scans WHERE id NOT IN (SELECT id FROM scans ORDER BY id DESC LIMIT {MAX_SCANS})")
            conn.commit()
        finally:
            conn.close()

    def save_trade(self, action, price, qty, pnl=0, reason="", entry_price=0, mode="SIM"):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO trades (created_at, action, price, qty, pnl, reason, entry_price, mode) VALUES (?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(), action, price, qty, pnl, reason, entry_price, mode)
            )
            conn.commit()
        finally:
            conn.close()

    def save_signal(self, action, price, confidence, notified_to="telegram"):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO signals (created_at, action, price, confidence, notified_to) VALUES (?,?,?,?,?)",
                (datetime.now().isoformat(), action, price, confidence, notified_to)
            )
            conn.commit()
        finally:
            conn.close()

    def get_stats(self):
        conn = self._conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM trades WHERE action='SELL'").fetchone()[0]
            wins = conn.execute("SELECT COUNT(*) FROM trades WHERE action='SELL' AND pnl > 0").fetchone()[0]
            losses = conn.execute("SELECT COUNT(*) FROM trades WHERE action='SELL' AND pnl < 0").fetchone()[0]
            total_pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE action='SELL'").fetchone()[0]
            scan_count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
            total_buys = conn.execute("SELECT COUNT(*) FROM trades WHERE action='BUY'").fetchone()[0]
            return {
                "toplam_islem": total,
                "kazanma": wins,
                "kaybetme": losses,
                "kazanma_orani": round(wins / total * 100, 1) if total > 0 else 0,
                "toplam_kar_zarar": round(total_pnl, 2),
                "toplam_tarama": scan_count,
                "toplam_alim": total_buys,
            }
        finally:
            conn.close()

    def get_trade_history(self, limit=50):
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT created_at, action, price, qty, pnl, reason, entry_price, mode FROM trades ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [
                {
                    "time": r[0],
                    "action": r[1],
                    "price": r[2],
                    "qty": r[3],
                    "pnl": round(r[4], 2) if r[4] else 0,
                    "reason": r[5] or "",
                    "entry_price": r[6] or 0,
                    "mode": r[7] or "SIM",
                }
                for r in rows
            ]
        finally:
            conn.close()

    def get_recent_scans(self, limit=20):
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT created_at, price, rsi, ema_cross, macd_hist, action, confidence, system_log FROM scans ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [
                {
                    "time": r[0],
                    "price": r[1],
                    "rsi": r[2],
                    "ema_cross": r[3],
                    "macd_hist": r[4],
                    "action": r[5],
                    "confidence": r[6],
                    "system_log": r[7] or "",
                }
                for r in rows
            ]
        finally:
            conn.close()

    def save_decision(self, strategy_action, strategy_score, strategy_reason, ai_prob, ai_veto, final_action, final_reason, price, executed=0):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO decisions (created_at, strategy_action, strategy_score, strategy_reason, ai_prob, ai_veto, final_action, final_reason, price, executed) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(), strategy_action, strategy_score, strategy_reason, ai_prob, 1 if ai_veto else 0, final_action, final_reason, price, 1 if executed else 0)
            )
            count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            if count > 500:
                conn.execute("DELETE FROM decisions WHERE id NOT IN (SELECT id FROM decisions ORDER BY id DESC LIMIT 500)")
            conn.commit()
        finally:
            conn.close()

    def get_decisions(self, limit=20):
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT created_at, strategy_action, strategy_score, strategy_reason, ai_prob, ai_veto, final_action, final_reason, price, executed FROM decisions ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [
                {
                    "time": r[0],
                    "strategy_action": r[1] or "---",
                    "strategy_score": r[2] or 0,
                    "strategy_reason": r[3] or "",
                    "ai_prob": r[4] or 0.5,
                    "ai_veto": bool(r[5]),
                    "final_action": r[6] or "HOLD",
                    "final_reason": r[7] or "",
                    "price": r[8] or 0,
                    "executed": bool(r[9]),
                }
                for r in rows
            ]
        finally:
            conn.close()


db = Database()
