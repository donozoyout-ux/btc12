"""
Gemini 5-Brain AI Debate Consensus System
==========================================
5 uzman AI kişiliği (Gemini LLM) piyasa verilerini tartışır ve ortak karara varır.
Her beyin kendi uzmanlık alanına göre argüman üretir.
Mevcut ML tabanlı ajanlarla (agents.py) birlikte çalışır - onları TAMAMLAR, değiştirmez.
"""

import json
import time
from datetime import datetime
from src.config import settings

# Gemini client - lazy init
_GEMINI_MODEL = None
_LAST_DEBATE = None
_LAST_DEBATE_TIME = 0
_DEBATE_COOLDOWN = 30  # Saniye - her taramada çağırmamak için


def _get_model():
    """Gemini modelini lazy-init et."""
    global _GEMINI_MODEL
    if _GEMINI_MODEL is not None:
        return _GEMINI_MODEL
    if not settings.gemini_api_key:
        print("[GEMINI] API key yok, LLM debate devre disi.")
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        _GEMINI_MODEL = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config={
                "temperature": 0.7,
                "top_p": 0.9,
                "max_output_tokens": 2048,
                "response_mime_type": "application/json",
            },
        )
        print("[GEMINI] Model basariyla yuklendi (gemini-2.5-flash)")
        return _GEMINI_MODEL
    except Exception as e:
        print(f"[GEMINI] Model yukleme hatasi: {e}")
        return None


SYSTEM_PROMPT = """Sen bir kripto para uzman paneli koordinatörüsün. 5 farklı uzman beyinin tartışmasını simüle edeceksin.

## 5 UZMAN BEYİN:

1. **TREND (Trend & Momentum Stratejisti)**: EMA kesişimleri, MACD momentumu, fiyat trendleri ve sling shot renklerine odaklanır. Trend takipçisidir.

2. **VOLATILITE (Volatilite & Mean Reversion Analisti)**: RSI aşırı alım/satım bölgeleri, StochRSI, Bollinger Band pozisyonu ve ATR volatilitesine odaklanır. Ortalamaya dönüşü arar.

3. **HACIM (Orderbook & Hacim Uzmanı)**: Alım/satım hacim oranı, orderbook dengesizliği (bid/ask ratio), hacimle teyit edilen hareketlere odaklanır.

4. **SEVİYE (Destek/Direnç & Kırılım Mimarı)**: Fiyatın destek ve direnç seviyelerine göre konumunu, kırılım sinyallerini ve Bollinger Band sınırlarını analiz eder.

5. **DUYGU (Makro Duygu & Haber Analisti)**: Son haberlerin duygusal tonunu, Fear & Greed endeksini ve piyasa psikolojisini değerlendirir. Contrarian (karşıt) bakış açısı sunar.

## KURALLAR:
- Her beyin KENDİ uzmanlık alanındaki verilere dayanarak 2-3 cümlelik argüman üretmeli.
- Her beyin BUY, SELL veya HOLD oylamalı ve 0.0-1.0 arası güven puanı vermeli.
- Argümanlar TÜRKÇE olmalı.
- Sonunda 5 beyinin oylarına göre final karar verilmeli (çoğunluk).
- SADECE aşağıdaki JSON formatında cevap ver, başka hiçbir şey yazma.

## ÇIKTI FORMATI (SADECE JSON):
{
  "brains": [
    {"name": "TREND", "vote": "BUY|SELL|HOLD", "confidence": 0.0-1.0, "argument": "..."},
    {"name": "VOLATILITE", "vote": "BUY|SELL|HOLD", "confidence": 0.0-1.0, "argument": "..."},
    {"name": "HACIM", "vote": "BUY|SELL|HOLD", "confidence": 0.0-1.0, "argument": "..."},
    {"name": "SEVİYE", "vote": "BUY|SELL|HOLD", "confidence": 0.0-1.0, "argument": "..."},
    {"name": "DUYGU", "vote": "BUY|SELL|HOLD", "confidence": 0.0-1.0, "argument": "..."}
  ],
  "final_decision": "BUY|SELL|HOLD",
  "final_confidence": 0.0-1.0,
  "summary": "1-2 cümlelik genel değerlendirme"
}"""


def _build_brain_instructions(brains=None):
    """Kullanıcının düzenlediği beyin talimatlarını prompt'a enjekte eder."""
    if not brains:
        try:
            from src import ai_brains
            brains = ai_brains.load_brains()
        except Exception:
            return ""
    lines = []
    for key in ["trend", "volatility", "volume", "level", "sentiment"]:
        b = brains.get(key)
        if not b or not b.get("enabled", True):
            continue
        name = b.get("label", key).upper()
        instr = b.get("instruction", "")
        if instr:
            lines.append(f"- {name}: {instr}")
    if not lines:
        return ""
    return "\n\n### UZMANLIK TALİMATLARI (Kullanıcı tanımlı)\n" + "\n".join(lines)


def _build_market_context(teknik, haberler=None, ml_votes=None):
    """Piyasa verilerinden Gemini'ye gönderilecek metin oluştur."""
    if not teknik or "price" not in teknik:
        return None

    price = teknik["price"]
    rsi = teknik.get("rsi", 50)
    ema_cross = teknik.get("ema_cross", "?")
    ema_dist = teknik.get("ema_dist", 0)
    macd_hist = teknik.get("macd_hist", 0)
    macd_hist_prev = teknik.get("macd_hist_prev", 0)
    bb_pct = teknik.get("bb_pct", 0.5)
    vol_ratio = teknik.get("vol_ratio", 1.0)
    atr = teknik.get("atr", 0)
    atr_pct = teknik.get("atr_pct", 0)
    support = teknik.get("support", 0)
    resistance = teknik.get("resistance", 0)
    breakout_up = teknik.get("breakout_up", 0)
    breakout_down = teknik.get("breakout_down", 0)
    stoch_rsi = teknik.get("stoch_rsi", 50)
    price_change_5 = teknik.get("price_change_5", 0)
    sling_color = teknik.get("sling_color", "?")

    ob = teknik.get("orderbook", {})
    ob_ratio = ob.get("bid_ask_ratio", 1.0)
    ob_sinyal = ob.get("bid_ask_sinyal", "notr")
    spread = ob.get("spread", 0)

    ctx = f"""## CANLI PİYASA VERİLERİ ({settings.symbol})
Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Fiyat: {price:,.2f}
Son 5-bar Değişim: %{price_change_5:.2f}

### TREND & MOMENTUM
- EMA Kesişim: {ema_cross.upper()}
- EMA Mesafesi: %{ema_dist:.2f}
- MACD Histogram: {macd_hist:.4f} (önceki: {macd_hist_prev:.4f})
- MACD Yön: {"Yükseliyor" if macd_hist > macd_hist_prev else "Düşüyor"}
- Sling Shot Rengi: {sling_color}

### VOLATİLİTE & OSİLATÖRLER
- RSI (14): {rsi:.1f}
- StochRSI: {stoch_rsi:.1f}
- Bollinger %B: {bb_pct:.3f}
- ATR: {atr:.2f} (%{atr_pct:.2f})

### HACİM & ORDERBOOK
- Hacim Oranı: {vol_ratio:.2f}x
- Orderbook Bid/Ask Oranı: {ob_ratio:.3f}
- Orderbook Sinyali: {ob_sinyal}
- Spread: {spread:.2f}

### DESTEK & DİRENÇ
- Destek: {support:,.2f}
- Direnç: {resistance:,.2f}
- Yukarı Kırılım: {"EVET" if breakout_up else "Hayır"}
- Aşağı Kırılım: {"EVET" if breakout_down else "Hayır"}
"""

    # Haberler
    if haberler and len(haberler) > 0:
        ctx += "\n### SON HABERLER\n"
        for h in haberler[:5]:
            baslik = h.get("baslik", "")
            sentiment = h.get("sentiment", "notr")
            ctx += f"- [{sentiment.upper()}] {baslik}\n"

    # ML Ajan Oyları (mevcut agents.py sistemi)
    if ml_votes:
        ctx += "\n### ML AJAN OYLAMASI (Mevcut Sistem)\n"
        for name, vote in ml_votes.items():
            if name.startswith("_"):
                continue
            action = vote.get("action", "HOLD")
            conf = vote.get("confidence", 0)
            ctx += f"- {name}: {action} (%{conf*100:.0f})\n"

    return ctx


def run_debate(teknik, haberler=None, ml_votes=None, brains=None, lessons=None):
    """
    5 Gemini beyinli tartışma yürüt.
    Returns: debate dict veya None (API yoksa/hata varsa)
    """
    global _LAST_DEBATE, _LAST_DEBATE_TIME

    # Cooldown kontrolü
    now = time.time()
    if now - _LAST_DEBATE_TIME < _DEBATE_COOLDOWN and _LAST_DEBATE is not None:
        return _LAST_DEBATE

    model = _get_model()
    if model is None:
        return None

    context = _build_market_context(teknik, haberler, ml_votes)
    if context is None:
        return None

    brain_instructions = _build_brain_instructions(brains)

    lessons_text = ""
    if lessons:
        try:
            lessons_text = "\n\n### SISTEMIN ÖĞRENDİĞİ DERSLER (geçmiş işlemlerden)\n"
            for les in lessons[-6:]:
                ls = les.get("lesson", "") if isinstance(les, dict) else str(les)
                lessons_text += f"- {ls}\n"
            lessons_text += "\nBu dersleri dikkate al: başarısız olan yaklaşımlardan kaçın, işe yarayanı güçlendir."
        except Exception:
            lessons_text = ""

    try:
        prompt = f"{SYSTEM_PROMPT}{brain_instructions}{lessons_text}\n\n{context}\n\nYukarıdaki verileri analiz et ve 5 uzman beyinin tartışmasını simüle et."

        response = model.generate_content(prompt)
        text = response.text.strip()

        # JSON parse
        debate = json.loads(text)

        # Doğrulama
        if "brains" not in debate or len(debate.get("brains", [])) != 5:
            print(f"[GEMINI] Gecersiz cikti formati, brains eksik/hatali")
            return _LAST_DEBATE

        # Meta veriler ekle
        debate["timestamp"] = datetime.now().isoformat()
        debate["symbol"] = settings.symbol
        debate["price"] = teknik.get("price", 0)

        # Oy sayımı
        buy_count = sum(1 for b in debate["brains"] if b.get("vote") == "BUY")
        sell_count = sum(1 for b in debate["brains"] if b.get("vote") == "SELL")
        hold_count = sum(1 for b in debate["brains"] if b.get("vote") == "HOLD")
        debate["buy_count"] = buy_count
        debate["sell_count"] = sell_count
        debate["hold_count"] = hold_count

        _LAST_DEBATE = debate
        _LAST_DEBATE_TIME = now

        fd = debate.get("final_decision", "HOLD")
        fc = debate.get("final_confidence", 0)
        print(f"[GEMINI] Debate tamamlandi: {fd} (%{fc*100:.0f}) | AL:{buy_count} SAT:{sell_count} BEKLE:{hold_count}")
        for b in debate["brains"]:
            print(f"  [{b['name']}] {b['vote']} (%{b['confidence']*100:.0f}): {b['argument'][:80]}")

        return debate

    except json.JSONDecodeError as e:
        print(f"[GEMINI] JSON parse hatasi: {e}")
        return _LAST_DEBATE
    except Exception as e:
        print(f"[GEMINI] Debate hatasi: {e}")
        return _LAST_DEBATE


def get_last_debate():
    """Panel'de göstermek için son tartışma sonucunu döndür."""
    return _LAST_DEBATE
