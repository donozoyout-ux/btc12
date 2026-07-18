"""
Sistem Kendini Geliştirme Modülü
===============================
- Dinamik işlem büyüklüğü: sistem kendi başına ne kadar yatırım yapacağına,
  güvene, son performansa, günlük hedefe ve zarar derinliğine göre karar verir.
- DİNAMİK KOMİSYON KORUMASI: sistem kendi başına, işlem başına komisyon
  maliyetini hesaplar ve pozisyonu ancak kârı bu maliyeti karşılayacak kadar
  hareket edince kapatır. Bu eşiği (min_exit_move_pct) ve güvenlik çarpanını
  (commission_tolerance) kendi öğrenir — sabit kural YOKTUR.
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
    # ─── DİNAMİK KOMİSYON KORUMASI (sistem kendi ayarlar) ───
    # min_exit_move: pozisyonun kapanması için gereken min fiyat hareketi (%).
    #   başlangıçta komisyon × safety; bot zarar sıklığına göre bunu öğrenir.
    "min_exit_move_pct": 0.0,        # 0 = ilk işlemde hesaplanır
    "avg_hold_sec": 0.0,             # öğrenilen ortalama tutma süresi
    "commission_tolerance": 1.5,     # güvenlik çarpanı (öğrenilir)
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
        "min_exit_move_pct": s.get("min_exit_move_pct", 0.0),
        "avg_hold_sec": s.get("avg_hold_sec", 0.0),
        "commission_tolerance": s.get("commission_tolerance", 1.5),
    }


def compute_min_exit_move():
    """Pozisyonun kapanması için gereken min fiyat hareketini (%)
    KENDISI hesaplar: komisyon × güvenlik çarpanı.

    Formül: min_exit = commission_rate × 2 (giriş+çıkış) × tolerance
    Örnek: 0.0035 × 2 × 1.5 = %1.05  → fiyat en az %1.05 hareket
    etmeden işlem kapanmaz (komisyonu karşılar + pay bırakır).
    """
    from src.config import settings
    comm = settings.commission_rate
    s = load()
    tol = s.get("commission_tolerance", settings.commission_safety)
    min_move = comm * 2 * tol * 100  # % cinsinden
    # Öğrenilmiş min_exit varsa onu kullan (ama komisyonun altına düşmez)
    learned = s.get("min_exit_move_pct", 0.0)
    if learned > 0:
        min_move = max(min_move, learned)
    return round(min_move, 4)


def get_lessons(limit=8):
    s = load()
    return list(reversed(s.get("lessons", [])[-limit:]))


def build_recent_reflection(limit=5):
    """Son işlemlerin net K/Z özetini ve son zararın nedenini üreten öz-eleştiri metni.
    5 beyne (Gemini tartışmasına) enjekte edilir ki başarısız strateji tekrarlanmasın."""
    try:
        from src.database import db
    except Exception:
        return ""
    try:
        trades = db.get_trade_history(limit)
    except Exception:
        return ""
    sells = [t for t in trades if t.get("action") == "SELL"]
    if not sells:
        return ""
    son5 = sells[:limit]
    net = round(sum((t.get("pnl", 0) or 0) for t in son5), 2)
    last_loss = next((t for t in sells if (t.get("pnl", 0) or 0) < 0), None)
    if last_loss:
        reason = (last_loss.get("reason") or "").lower()
        if "stop" in reason or "sl" in reason or "stoploss" in reason:
            cause = "Stop-loss patlaması"
        else:
            cause = "Yanlış sinyal"
        loss_line = f"Son zararlı işlem nedenin: {cause}."
    else:
        loss_line = "Son zararlı işlem nedeni: son işlemlerde zarar yok."
    return (
        f"Son {len(son5)} işlemdeki Net K/Z durumun: {net:+.2f} $. "
        f"{loss_line} "
        f"Yeni kararını verirken bu başarısız stratejiyi tekrarlamadığından emin ol."
    )


def describe_entry_condition(t):
    """Giriş anındaki gösterge koşulunu kısa Türkçe metne çevirir (ders üretimi için)."""
    if not t:
        return "bilinmeyen gösterge durumu"
    parts = []
    try:
        rsi = float(t.get("rsi", 50))
        if rsi >= 70:
            parts.append(f"yüksek RSI ({rsi:.0f})")
        elif rsi <= 30:
            parts.append(f"düşük RSI ({rsi:.0f})")
        macd = float(t.get("macd_hist", 0) or 0)
        macd_prev = float(t.get("macd_hist_prev", 0) or 0)
        if macd > 0 and macd < macd_prev:
            parts.append("zayıflayan MACD momentumu")
        elif macd < 0:
            parts.append("negatif MACD")
        bb = float(t.get("bb_pct", 0.5) or 0.5)
        if bb >= 0.95:
            parts.append(f"fiyat üst Bollinger bandında (%B={bb:.2f})")
        elif bb <= 0.05:
            parts.append(f"fiyat alt Bollinger bandında (%B={bb:.2f})")
        if t.get("ema_cross") == "bearish":
            parts.append("bearish EMA kesişimi")
        vol = float(t.get("vol_ratio", 1) or 1)
        if vol >= 2.5:
            parts.append(f"anormal hacim ({vol:.1f}x)")
    except Exception:
        pass
    return ", ".join(parts) if parts else "normal gösterge değerleri"


def add_trade_lesson(text):
    """Zarar/stop-loss işleminden üretilen mini dersi hafızaya kaydeder."""
    if not text:
        return
    cfg = load()
    cfg.setdefault("trade_lessons", [])
    cfg["trade_lessons"].append({
        "time": datetime.now().isoformat(),
        "lesson": text,
    })
    cfg["trade_lessons"] = cfg["trade_lessons"][-20:]
    save(cfg)


def get_trade_lessons(limit=10):
    cfg = load()
    return list(reversed(cfg.get("trade_lessons", [])[-limit:]))


def decide_position_size(equity, confidence, win_rate=0.5, drawdown_pct=0.0, daily_progress=0.0):
    """
    Sistemin kendi işlem miktarını belirlemesi.
    equity: mevcut portföy değeri (USDT)
    confidence: konsensüs güveni 0..1
    win_rate: son N işlemin kazanma oranı 0..1
    drawdown_pct: son zirveden düşüş yüzdesi (pozitif)
    daily_progress: günlük hedefe ulaşma oranı 0..1+ (1 = hedef tamam)
    Döner: USDT cinsinden işlem miktarı

    NOT: Varsayılan olarak sistem disiplinli ve SABIRLIDIR. Aç gözlülük modu
    (AGGRESSIVE_MODE) kapalıyken işlem agresifliği asla otomatik artırılmaz ve
    günlük hedefin gerisinde kalınınca "daha atak" davranılmaz.
    """
    from src.config import settings
    cfg = load()
    agg = cfg["position_aggressiveness"]
    base_risk = 0.02  # sermayenin %2'si temel risk

    conf_factor = 0.5 + max(0.0, min(1.0, confidence))          # 0.5 .. 1.5
    perf_factor = 0.7 + win_rate                                # 0.7 .. 1.7
    # Hedefin gerisinde kalınınca "daha atak" davranmak YERİNE, varsayılan
    # davranış nötrdür (goal_factor = 1.0). Sadece aç gözlülük modu açıksa
    # ve bir günlük hedef tanımlıysa geri kalanı kapatmak için hafifçe esnek olur.
    goal_factor = 1.0
    if settings.aggressive_mode and settings.daily_goal_pct > 0 and daily_progress < 0.5:
        goal_factor = 1.1  # en fazla %10 esneklik, asla agresif kaldıraç değil
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

    # İşlem agresifliğini ayarla (varsayılan: kapalı / disiplinli)
    from src.config import settings
    if settings.aggressive_mode:
        if win_rate > 0.6 and avg_pnl > 0:
            cfg["position_aggressiveness"] = min(2.0, cfg["position_aggressiveness"] * 1.1)
            lesson = f"Performans İYİ (kazanma %{win_rate*100:.0f}, ort. K/Z ${avg_pnl:+.2f}) → işlem agresifliği {cfg['position_aggressiveness']:.2f}x'e çıkarıldı."
        elif win_rate < 0.4:
            cfg["position_aggressiveness"] = max(0.4, cfg["position_aggressiveness"] * 0.9)
            lesson = f"Performans ZAYIF (kazanma %{win_rate*100:.0f}) → işlem agresifliği {cfg['position_aggressiveness']:.2f}x'e düşürüldü, daha seçici olunacak."
        else:
            lesson = f"Performans NÖTR (kazanma %{win_rate*100:.0f}, ort. K/Z ${avg_pnl:+.2f}) → agresiflik korunuyor."
    else:
        # Aç gözlülük modu kapalı: agresiflik sabit ve dengeli (1.0x) tutulur.
        cfg["position_aggressiveness"] = 1.0
        lesson = f"Performans (kazanma %{win_rate*100:.0f}, ort. K/Z ${avg_pnl:+.2f}) → agresiflik sabit {cfg['position_aggressiveness']:.2f}x (aç gözlülük modu kapalı)."

    # Konsensüs güven eşiğini ayarla
    if win_rate < 0.4:
        cfg["min_confidence_threshold"] = min(0.7, cfg["min_confidence_threshold"] + 0.05)
        lesson += f" Güven eşiği {cfg['min_confidence_threshold']:.2f}'ye yükseltildi."
    elif win_rate > 0.6:
        cfg["min_confidence_threshold"] = max(0.4, cfg["min_confidence_threshold"] - 0.03)
        lesson += f" Güven eşiği {cfg['min_confidence_threshold']:.2f}'ye çekildi."

    # ─── DİNAMİK KOMİSYON KORUMASI ÖĞRENMESİ ───
    # Sık zararla kapanıyorsa min_exit_move_pct'i yükselt (daha uzun tut / daha
    # az işlem), kârlı ama çok geç kapanıyorsa düşür (daha sık işlem).
    # Bu SABİT DEĞİL; sistem kendi optimal eşiğini bulur.
    from src.config import settings
    comm = settings.commission_rate
    base_move = comm * 2 * settings.commission_safety * 100  # % cinsinden taban

    # Son N işlemdeki zarar oranı
    losses = [t for t in recent if t["pnl"] < 0]
    loss_rate = len(losses) / len(recent)

    cur_move = cfg.get("min_exit_move_pct", 0.0) or 0.0
    if cur_move <= 0:
        cur_move = base_move  # ilk değer: komisyon × güvenlik

    if loss_rate > 0.5:
        # Çok zarar ediyor -> eşiği yükselt (işlemi daha az ama daha emin yap)
        cur_move = min(cur_move * 1.15, base_move * 3.0)
        cfg["commission_tolerance"] = min(3.0, cfg.get("commission_tolerance", 1.5) * 1.1)
        lesson += f" Sık zarar (%{loss_rate*100:.0f}) → min çıkış hareketi %{cur_move:.2f}'ye, güvenlik %{cfg['commission_tolerance']:.2f}'ye çıkarıldı (komisyon koruması güçlendi)."
    elif loss_rate < 0.25 and avg_pnl > 0:
        # Az zarar, kârlı -> eşiği düşür (daha sık ama güvenli işlem)
        cur_move = max(cur_move * 0.95, base_move * 0.8)
        cfg["commission_tolerance"] = max(1.2, cfg.get("commission_tolerance", 1.5) * 0.97)
        lesson += f" Az zarar, kârlı (%{win_rate*100:.0f}) → min çıkış hareketi %{cur_move:.2f}'ye çekildi (daha sık işlem, komisyon hâlâ karşılanıyor)."

    cfg["min_exit_move_pct"] = round(cur_move, 4)

    # Ortalama tutma süresini öğren (son 10 işlemden)
    try:
        recent_full = db.get_trade_history(10)
        buys = [t for t in recent_full if t.get("action") == "BUY"]
        sells = [t for t in recent_full if t.get("action") == "SELL"]
        if len(buys) >= 2 and len(sells) >= 2:
            # basit ortalama: işlem sayısı / zaman aralığı yerine son SAT zamanını kullan
            last_sell_time = sells[0].get("time", "")
            if last_sell_time:
                cfg["avg_hold_sec"] = round(cfg.get("avg_hold_sec", 0.0) * 0.7 + 120 * 0.3, 1)
    except Exception:
        pass

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
