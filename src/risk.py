import json
import os
import threading
from datetime import datetime

# ──────────────────────────────────────────────────────────────
#  GLOBAL RİSK KONTROL KATMANI (Kill Switch / Panic Button)
#  Tek bir global durum tutar: ACTIVE  veya  EMERGENCY_STOP
#  Durum risk_state.json dosyasına kalıcı olarak yazılır ki
#  servis yeniden başlasa bile acil durum korunsun.
# ──────────────────────────────────────────────────────────────

STATE_FILE = "risk_state.json"
_lock = threading.Lock()

DEFAULT = {
    "mode": "ACTIVE",          # ACTIVE | EMERGENCY_STOP
    "emergency_at": None,
    "resumed_at": None,
    "reason": None,
    "log": [],                  # son 50 olay
}


def _load():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT.items():
                data.setdefault(k, v)
            return data
        except Exception as e:
            print(f"[RISK] state yukleme hatasi: {e}")
    return dict(DEFAULT)


def _save(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[RISK] state kaydetme hatasi: {e}")


def is_emergency():
    """Tüm ajanların ve executor'ın işlem yapmadan önce çağıracağı guard."""
    try:
        return _load()["mode"] == "EMERGENCY_STOP"
    except Exception:
        return False


def get_status():
    s = _load()
    return {
        "mode": s["mode"],
        "emergency_at": s["emergency_at"],
        "resumed_at": s["resumed_at"],
        "reason": s["reason"],
        "log": s.get("log", [])[-20:],
    }


def trigger(bot, reason="Manuel panic button (dashboard)"):
    """ACİL DURDURMA: tüm otonom döngüleri durdur, açık emirleri iptal et."""
    with _lock:
        s = _load()
        if s["mode"] == "EMERGENCY_STOP":
            return s
        now = datetime.now().isoformat(timespec="seconds")
        s["mode"] = "EMERGENCY_STOP"
        s["emergency_at"] = now
        s["reason"] = reason
        s.setdefault("log", []).append({"time": now, "event": "KILL_SWITCH", "reason": reason})
        s["log"] = s["log"][-50:]
        _save(s)

    # 1) Tüm aktif otonom döngüleri durdur
    try:
        bot.running = False
        bot.paused = False
    except Exception as e:
        print(f"[RISK] bot durdurma hatasi: {e}")

    # 2) Borsa entegrasyonundaki açık emirleri iptal et
    try:
        from src.executor import executor
        executor.cancel_open_orders()
    except Exception as e:
        print(f"[RISK] acik emir iptal hatasi: {e}")

    # 3) Logla + Telegram bildirimi
    print(f"[RISK] 🛑 KILL SWITCH AKTİF @ {reason}")
    try:
        from src.telegram import tg
        tg.send("🛑 <b>ACİL DURDURMA (KILL SWITCH)</b> tetiklendi.\nTüm otonom işlemler ve açık emirler durduruldu.")
    except Exception:
        pass

    return s


def resume(bot, reason="Manuel resume (dashboard)"):
    """Sistemi ACTIVE moda al ve ajan döngülerini yeniden başlatılabilir kıl."""
    with _lock:
        s = _load()
        now = datetime.now().isoformat(timespec="seconds")
        s["mode"] = "ACTIVE"
        s["resumed_at"] = now
        s["reason"] = reason
        s.setdefault("log", []).append({"time": now, "event": "RESUME", "reason": reason})
        s["log"] = s["log"][-50:]
        _save(s)

    # Ajan döngülerini yeniden başlat
    try:
        bot.start(mesaj_gonder=False)
    except Exception as e:
        print(f"[RISK] resume baslatma hatasi: {e}")

    print(f"[RISK] ✅ SİSTEM YENİDEN AKTİF @ {reason}")
    try:
        from src.telegram import tg
        tg.send("✅ <b>SİSTEM YENİDEN BAŞLATILDI</b> (RESUME). Otonom işlemler devam ediyor.")
    except Exception:
        pass

    return s
