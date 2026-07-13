import os
import json
import base64
from datetime import datetime

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
_SUPABASE_CLIENT = None


def _client():
    global _SUPABASE_CLIENT
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    if _SUPABASE_CLIENT is None:
        try:
            from supabase import create_client
            _SUPABASE_CLIENT = create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"[SUPABASE] Baglanti hatasi: {e}")
    return _SUPABASE_CLIENT


def is_connected():
    return _client() is not None


def save_trade(action, price, qty, pnl, reason, entry_price, mode):
    c = _client()
    if not c:
        return
    try:
        c.table("trades").insert({
            "created_at": datetime.now().isoformat(),
            "action": action,
            "price": price,
            "qty": qty,
            "pnl": pnl,
            "reason": reason,
            "entry_price": entry_price,
            "mode": mode,
        }).execute()
    except Exception as e:
        print(f"[SUPABASE] save_trade hatasi: {e}")


def save_scan(price, rsi, ema_cross, macd_hist, vol_ratio, haber_sentiment, action, confidence, stop_loss, take_profit, system_log):
    c = _client()
    if not c:
        return
    try:
        c.table("scans").insert({
            "created_at": datetime.now().isoformat(),
            "price": price,
            "rsi": rsi,
            "ema_cross": str(ema_cross) if ema_cross else None,
            "macd_hist": macd_hist,
            "vol_ratio": vol_ratio,
            "haber_sentiment": haber_sentiment,
            "action": action,
            "confidence": confidence,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "system_log": system_log,
        }).execute()
    except Exception as e:
        print(f"[SUPABASE] save_scan hatasi: {e}")


def save_decision(strategy_action, strategy_score, strategy_reason, ai_prob, ai_veto, final_action, final_reason, price, executed):
    c = _client()
    if not c:
        return
    try:
        c.table("decisions").insert({
            "created_at": datetime.now().isoformat(),
            "strategy_action": strategy_action,
            "strategy_score": strategy_score,
            "strategy_reason": strategy_reason,
            "ai_prob": ai_prob,
            "ai_veto": 1 if ai_veto else 0,
            "final_action": final_action,
            "final_reason": final_reason,
            "price": price,
            "executed": 1 if executed else 0,
        }).execute()
    except Exception as e:
        print(f"[SUPABASE] save_decision hatasi: {e}")


def save_executor_state(balance, btc, entry):
    c = _client()
    if not c:
        return
    try:
        existing = c.table("executor_state").select("*").limit(1).execute()
        data = {"balance": balance, "btc": btc, "entry": entry, "updated_at": datetime.now().isoformat()}
        if existing.data and len(existing.data) > 0:
            c.table("executor_state").update(data).eq("id", existing.data[0]["id"]).execute()
        else:
            c.table("executor_state").insert(data).execute()
    except Exception as e:
        print(f"[SUPABASE] save_executor_state hatasi: {e}")


def load_executor_state():
    c = _client()
    if not c:
        return None
    try:
        result = c.table("executor_state").select("*").limit(1).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
    except Exception as e:
        print(f"[SUPABASE] load_executor_state hatasi: {e}")
    return None


def save_ai_model(model_binary, accuracy, prediction_count):
    c = _client()
    if not c:
        return
    try:
        b64 = base64.b64encode(model_binary).decode("ascii") if model_binary else ""
        existing = c.table("ai_model").select("*").limit(1).execute()
        data = {"model_data": b64, "accuracy": accuracy, "prediction_count": prediction_count, "updated_at": datetime.now().isoformat()}
        if existing.data and len(existing.data) > 0:
            c.table("ai_model").update(data).eq("id", existing.data[0]["id"]).execute()
        else:
            c.table("ai_model").insert(data).execute()
    except Exception as e:
        print(f"[SUPABASE] save_ai_model hatasi: {e}")


def load_ai_model():
    c = _client()
    if not c:
        return None
    try:
        result = c.table("ai_model").select("*").limit(1).execute()
        if result.data and len(result.data) > 0:
            row = result.data[0]
            b64 = row.get("model_data", "")
            model_binary = base64.b64decode(b64) if b64 else None
            return {
                "model": model_binary,
                "accuracy": row.get("accuracy", 0.0),
                "prediction_count": row.get("prediction_count", 0),
            }
    except Exception as e:
        print(f"[SUPABASE] load_ai_model hatasi: {e}")
    return None


def save_ai_memory(features, future_return, predicted_prob, actual_direction, pnl):
    c = _client()
    if not c:
        return
    try:
        c.table("ai_memory").insert({
            "created_at": datetime.now().isoformat(),
            "features": json.dumps(features),
            "future_return": future_return,
            "predicted_prob": predicted_prob,
            "actual_direction": actual_direction,
            "pnl": pnl,
        }).execute()
    except Exception as e:
        print(f"[SUPABASE] save_ai_memory hatasi: {e}")


def load_ai_memory(limit=5000):
    c = _client()
    if not c:
        return []
    try:
        result = c.table("ai_memory").select("*").order("created_at", desc=False).limit(limit).execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"[SUPABASE] load_ai_memory hatasi: {e}")
        return []

def load_trades(limit=50):
    c = _client()
    if not c:
        return []
    try:
        res = c.table("trades").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"[SUPABASE] load_trades hatasi: {e}")
        return []


def load_scans(limit=20):
    c = _client()
    if not c:
        return []
    try:
        res = c.table("scans").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"[SUPABASE] load_scans hatasi: {e}")
        return []


def load_decisions(limit=20):
    c = _client()
    if not c:
        return []
    try:
        res = c.table("decisions").select("*").order("created_at", desc=True).limit(limit).execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"[SUPABASE] load_decisions hatasi: {e}")
        return []


def save_agent_state(state):
    c = _client()
    if not c:
        return
    try:
        existing = c.table("agent_state").select("*").limit(1).execute()
        data = {"state": state, "updated_at": datetime.now().isoformat()}
        if existing.data and len(existing.data) > 0:
            c.table("agent_state").update(data).eq("id", existing.data[0]["id"]).execute()
        else:
            c.table("agent_state").insert(data).execute()
    except Exception as e:
        print(f"[SUPABASE] save_agent_state hatasi: {e}")


def load_agent_state():
    c = _client()
    if not c:
        return None
    try:
        result = c.table("agent_state").select("*").limit(1).execute()
        if result.data and len(result.data) > 0:
            return result.data[0].get("state")
    except Exception as e:
        print(f"[SUPABASE] load_agent_state hatasi: {e}")
    return None


def save_consensus_states(data):
    """5 AI ajanının durumlarını (ağırlıklar, doğruluklar) kaydet."""
    c = _client()
    if not c:
        return
    try:
        existing = c.table("consensus_states").select("*").limit(1).execute()
        payload = {"states": data, "updated_at": datetime.now().isoformat()}
        if existing.data and len(existing.data) > 0:
            c.table("consensus_states").update(payload).eq("id", existing.data[0]["id"]).execute()
        else:
            c.table("consensus_states").insert(payload).execute()
    except Exception as e:
        print(f"[SUPABASE] save_consensus_states hatasi: {e}")


def load_consensus_states():
    """5 AI ajanının durumlarını Supabase'den yükle."""
    c = _client()
    if not c:
        return None
    try:
        result = c.table("consensus_states").select("*").limit(1).execute()
        if result.data and len(result.data) > 0:
            return result.data[0].get("states")
    except Exception as e:
        print(f"[SUPABASE] load_consensus_states hatasi: {e}")
    return None


def delete_old_scans():
    """Supabase'deki eski scan kayitlarini temizle"""
    c = _client()
    if not c:
        return
    try:
        c.table("scans").delete().lt("created_at", datetime.now().isoformat()).execute()
    except:
        pass


def create_tables():
    """Supabase'de tablolari olustur (manuel SQL ile)"""
    print("[SUPABASE] Tablolar Supabase dashboard'dan SQL Editor ile olusturulmali:")
    print("""
    CREATE TABLE trades (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        action TEXT, price REAL, qty REAL, pnl REAL,
        reason TEXT, entry_price REAL, mode TEXT DEFAULT 'SIM'
    );
    CREATE TABLE scans (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        price REAL, rsi REAL, ema_cross TEXT,
        macd_hist REAL, vol_ratio REAL, haber_sentiment REAL,
        action TEXT, confidence REAL, stop_loss REAL,
        take_profit REAL, system_log TEXT
    );
    CREATE TABLE decisions (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        strategy_action TEXT, strategy_score REAL,
        strategy_reason TEXT, ai_prob REAL, ai_veto INT DEFAULT 0,
        final_action TEXT, final_reason TEXT, price REAL, executed INT DEFAULT 0
    );
    CREATE TABLE executor_state (
        id BIGSERIAL PRIMARY KEY,
        balance REAL, btc REAL, entry REAL, updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE ai_model (
        id BIGSERIAL PRIMARY KEY,
        model_data TEXT, accuracy REAL,
        prediction_count INT, updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE ai_memory (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        features JSONB, future_return REAL,
        predicted_prob REAL, actual_direction INT, pnl REAL
    );
    CREATE TABLE agent_state (
        id BIGSERIAL PRIMARY KEY,
        state JSONB,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE consensus_states (
        id BIGSERIAL PRIMARY KEY,
        states JSONB,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)


def reset_all():
    """Tüm ilgili Supabase tablolarını temizler (tam sıfırlama)."""
    try:
        c = _client()
        for table in ("scans", "trades", "decisions", "signals",
                      "ai_memory", "consensus_states", "agent_state"):
            try:
                c.table(table).delete().neq("id", -1).execute()
            except Exception as e:
                print(f"[SUPABASE] reset_all {table} hatasi: {e}")
        return True
    except Exception as e:
        print(f"[SUPABASE] reset_all hatasi: {e}")
        return False

