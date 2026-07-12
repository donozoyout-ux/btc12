"""
Sistem Kendini Geliştirme Modülü
================================
- Dinamik işlem büyüklüğü: sistem kendi başına ne kadar yatırım yapacağına,
  güvene, son performansa, günlük hedefe ve zarar derinliğine göre karar verir.
- Öz-değerlendirme: kapalı işlemleri inceler, ders çıkarır, ajan ağırlıklarını
  ve işlem agresifliğini otomatik ayarlar. Tüm öğrenilenler self_improve.json'a
  yazılır -> sistem yeniden başlasa bile hafızasını korur (sürekli gelişim).
"""

import json
import os
from datetime import datetime

MEMORY_FILE = "self_improve.json"

DEFAULT_STATE = {
    "position_aggressiveness": 1.0,   # 0.4 .. 2.0
    "min_confidence_threshold": 0.45,  # konsensüs güven alt sınırı
    "lessons": [],                     # öğrenilen dersler
    "last_review": None,
    "trades_since_review": 0,
    "total_reviews": 0,
}


def _path():
    if not os.path.exists("config"):
        os.makedirs("config", exist_ok=True)
    return os.path.join("config", "self_improve.json")


def load():
    p = _path()
    if not os.path.exists(p):
        return dict(DEFAULT_STATE)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT_STATE.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(DEFAULT_STATE)


def save(state):
    p = _path()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_params():
    s = load()
    return {
        "position_aggressiveness": s["position_aggressiveness"],
        "min_confidence_threshold": s["min_confidence_threshold"],
    }


def get_lessons(limit=8):
    s = load()
    return list(reversed(s.get("lessons", [])[-limit:]))


def decide_position_size(equity, confidence, win_rate=0.5, drawdown_pct=0.0, daily_progress=0.0):
    """
    Sistemin kendi işlem miktarını belirlemesi.
    equity: mevcut portföy değeri (USDT)
    confidence: konsensüs güveni 0..1
    win_rate: son N işlemin kazanma oranı 0..1
    drawdown_pct: son zirveden düşüş yüzdesi (pozitif)
    daily_progress: günlük %1 hedefine ulaşma oranı 0..1+ (1 = hedef tamam)
    Döner: USDT cinsinden işlem miktarı
    """
    cfg = load()
    agg = cfg["position_aggressiveness"]
    base_risk = 0.02  # sermayenin %2'si temel risk

    conf_factor = 0.5 + max(0.0, min(1.0, confidence))          # 0.5 .. 1.5
    perf_factor = 0.7 + win_rate                                # 0.7 .. 1.7
    goal_factor = 1.0 + (0.25 if daily_progress < 0.5 else -0.1)  # hedefin gerisindeyse daha atak
    dd_factor = max(0.3, 1.0 - max(0.0, drawdown_pct) / 20.0)   # büyük düşüşte kısıtla

    risk = base_risk * conf_factor * perf_factor * agg * goal_factor * dd_factor
    risk = min(risk, 0.25)     # tek işlemde sermayenin en fazla %25'i
    risk = max(risk, 0.005)    # en az %0.5

    amount = equity * risk
    return round(amount, 2)


def review_and_adapt(db, consensus):
    """Kapalı işlemleri inceleyip sistemi kendisi ayarlar. Dersi hafızaya yazar."""
    cfg = load()
    try:
        trades = db.get_trade_history(40)
    except Exception:
        trades = []
    closed = [t for t in trades if t.get("pnl") is not None and t.get("pnl") != 0]
    recent = closed[-20:]
    if len(recent) < 5:
        return None

    wins = sum(1 for t in recent if t["pnl"] > 0)
    win_rate = wins / len(recent)
    avg_pnl = sum(t["pnl"] for t in recent) / len(recent)

    # İşlem agresifliğini ayarla
    if win_rate > 0.6 and avg_pnl > 0:
        cfg["position_aggressiveness"] = min(2.0, cfg["position_aggressiveness"] * 1.1)
        lesson = f"Performans İYİ (kazanma %{win_rate*100:.0f}, ort. K/Z ${avg_pnl:+.2f}) → işlem agresifliği {cfg['position_aggressiveness']:.2f}x'e çıkarıldı."
    elif win_rate < 0.4:
        cfg["position_aggressiveness"] = max(0.4, cfg["position_aggressiveness"] * 0.9)
        lesson = f"Performans ZAYIF (kazanma %{win_rate*100:.0f}) → işlem agresifliği {cfg['position_aggressiveness']:.2f}x'e düşürüldü, daha seçici olunacak."
    else:
        lesson = f"Performans NÖTR (kazanma %{win_rate*100:.0f}, ort. K/Z ${avg_pnl:+.2f}) → agresiflik korunuyor."

    # Konsensüs güven eşiğini ayarla
    if win_rate < 0.4:
        cfg["min_confidence_threshold"] = min(0.7, cfg["min_confidence_threshold"] + 0.05)
        lesson += f" Güven eşiği {cfg['min_confidence_threshold']:.2f}'ye yükseltildi."
    elif win_rate > 0.6:
        cfg["min_confidence_threshold"] = max(0.4, cfg["min_confidence_threshold"] - 0.03)
        lesson += f" Güven eşiği {cfg['min_confidence_threshold']:.2f}'ye çekildi."

    # Zayıf ajan tespiti
    try:
        states = consensus.get_all_states()
        weak = [n for n, a in states.items()
                if isinstance(a, dict) and a.get("is_trained") and a.get("accuracy", 1) < 0.4]
        if weak:
            lesson += f" Zayıf ajan(lar): {', '.join(weak)} (ağırlıkları otomatik düşürüldü)."
    except Exception:
        weak = []

    cfg["lessons"].append({
        "time": datetime.now().isoformat(),
        "lesson": lesson,
        "win_rate": round(win_rate, 2),
        "avg_pnl": round(avg_pnl, 2),
    })
    cfg["lessons"] = cfg["lessons"][-40:]
    cfg["last_review"] = datetime.now().isoformat()
    cfg["total_reviews"] = cfg.get("total_reviews", 0) + 1
    cfg["trades_since_review"] = 0
    save(cfg)
    return lesson


def note_trade_closed():
    cfg = load()
    cfg["trades_since_review"] = cfg.get("trades_since_review", 0) + 1
    save(cfg)
    return cfg.get("trades_since_review", 0)
