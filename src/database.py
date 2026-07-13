import sqlite3
import os
from datetime import datetime
from src import supabase_store


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trades.db")
MAX_SCANS = 1000


class Database:
    def __init__(self):
        self._init_db()
        self.sync_from_supabase()

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
            supabase_store.save_scan(price, rsi, ema_cross, macd_hist, vol_ratio, haber_sentiment, action, confidence, stop_loss, take_profit, system_log)
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
            supabase_store.save_trade(action, price, qty, pnl, reason, entry_price, mode)
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

    def reset_all(self):
        """Tüm yerel ve Supabase verilerini (scans, trades, decisions, signals) sıfırlar."""
        conn = self._conn()
        try:
            conn.execute("DELETE FROM scans")
            conn.execute("DELETE FROM trades")
            conn.execute("DELETE FROM decisions")
            conn.execute("DELETE FROM signals")
            conn.commit()
        finally:
            conn.close()
        try:
            supabase_store.reset_all()
        except Exception as e:
            print(f"[DATABASE] Supabase reset hatasi (yok sayildi): {e}")
        return True

    def get_trade_pnl(self, limit=100):
        """Sadece kâr/zarar odaklı işlem geçmişi (tarih, aksiyon, pnl, mod)."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT created_at, action, pnl, mode FROM trades ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [
                {
                    "time": r[0],
                    "action": r[1],
                    "pnl": round(r[2], 2) if r[2] else 0,
                    "mode": r[3] or "SIM",
                }
                for r in rows
            ]
        finally:
            conn.close()
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
            supabase_store.save_decision(strategy_action, strategy_score, strategy_reason, ai_prob, ai_veto, final_action, final_reason, price, executed)
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

    def get_daily_pnl(self, limit=30):
        conn = self._conn()
        try:
            rows = conn.execute("""
                SELECT DATE(created_at) as gun, ROUND(SUM(pnl), 2), COUNT(*)
                FROM trades WHERE action='SELL'
                GROUP BY gun ORDER BY gun DESC LIMIT ?
            """, (limit,)).fetchall()
            rows.reverse()
            return [{"date": r[0], "pnl": r[1], "count": r[2]} for r in rows]
        finally:
            conn.close()

    def sync_from_supabase(self):
        if not supabase_store.is_connected():
            return
        print("[DATABASE] Supabase'den veri senkronizasyonu baslatiliyor...")
        try:
            conn = self._conn()
            
            # 1. Sync trades
            trade_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            if trade_count == 0:
                print("[DATABASE] Yerel trades tablosu bos, Supabase'den cekiliyor...")
                sb_trades = supabase_store.load_trades(100)
                for t in reversed(sb_trades):
                    conn.execute(
                        "INSERT INTO trades (created_at, action, price, qty, pnl, reason, entry_price, mode) VALUES (?,?,?,?,?,?,?,?)",
                        (t.get("created_at"), t.get("action"), t.get("price"), t.get("qty"), t.get("pnl"), t.get("reason"), t.get("entry_price"), t.get("mode", "SIM"))
                    )
                print(f"[DATABASE] {len(sb_trades)} adet islem basariyla senkronize edildi.")
            
            # 2. Sync scans
            scan_count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
            if scan_count == 0:
                print("[DATABASE] Yerel scans tablosu bos, Supabase'den cekiliyor...")
                sb_scans = supabase_store.load_scans(100)
                for s in reversed(sb_scans):
                    conn.execute(
                        "INSERT INTO scans (created_at, price, rsi, ema_cross, macd_hist, vol_ratio, haber_sentiment, action, confidence, stop_loss, take_profit, system_log) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (s.get("created_at"), s.get("price"), s.get("rsi"), s.get("ema_cross"), s.get("macd_hist"), s.get("vol_ratio"), s.get("haber_sentiment"), s.get("action"), s.get("confidence"), s.get("stop_loss"), s.get("take_profit"), s.get("system_log"))
                    )
                print(f"[DATABASE] {len(sb_scans)} adet tarama basariyla senkronize edildi.")

            # 3. Sync decisions
            decision_count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            if decision_count == 0:
                print("[DATABASE] Yerel decisions tablosu bos, Supabase'den cekiliyor...")
                sb_decisions = supabase_store.load_decisions(100)
                for d in reversed(sb_decisions):
                    conn.execute(
                        "INSERT INTO decisions (created_at, strategy_action, strategy_score, strategy_reason, ai_prob, ai_veto, final_action, final_reason, price, executed) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (d.get("created_at"), d.get("strategy_action"), d.get("strategy_score"), d.get("strategy_reason"), d.get("ai_prob"), d.get("ai_veto", 0), d.get("final_action"), d.get("final_reason"), d.get("price"), d.get("executed", 0))
                    )
                print(f"[DATABASE] {len(sb_decisions)} adet karar basariyla senkronize edildi.")

            conn.commit()
        except Exception as e:
            print(f"[DATABASE] Supabase senkronizasyon hatasi: {e}")
        finally:
            conn.close()


db = Database()
