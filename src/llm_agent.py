"""
Gemini 5-Brain AI Debate Consensus System
=========================================
5 uzman AI kişiliği (Gemini LLM) piyasa verilerini tartışır ve ortak karara varır.
Her beyin kendi uzmanlık alanına göre argüman üretir.

Her beyin, kullanıcının verdiği rol şablonuna göre (AJAN_ADI / AJAN_GÖREVİ /
analiz odağı) kişiliklendirilir. Son işlemlerin net K/Z özeti ("otonom öğrenme
logları") beyinlere beslenir; böylece başarısız strateji tekrarlanmaz.
Mevcut ML tabanlı ajanlarla (agents.py) birlikte çalışır - onları TAMAMLAR.
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


# Her beynin analiz odağı (AJAN_GÖREVİ şablonundaki "Analiz Odağın" yerine geçer)
_AGENT_FOCUS = {
    "trend": "EMA/MACD uyumu, trend yönü ve momentum",
    "volatility": "RSI, StochRSI ve Bollinger Band aşırı alım/satım bölgeleri",
    "volume": "Hacim oranı ve orderbook (bid/ask) dengesi",
    "level": "Destek/direnç seviyeleri ve kırılım sinyalleri",
    "sentiment": "Haber/duygu tonu, Fear & Greed endeksi ve makro psikoloji",
}

_ORDER = ["trend", "volatility", "volume", "level", "sentiment"]


def _build_agent_personas(brains=None):
    """Her beyne rol şablonunu uygular: AJAN_ADI + AJAN_GÖREVİ + analiz odağı."""
    if not brains:
        try:
            from src import ai_brains
            brains = ai_brains.load_brains()
        except Exception:
            return ""
    blocks = []
    for key in _ORDER:
        b = brains.get(key)
        if not b or not b.get("enabled", True):
            continue
        name = b.get("label", key).upper()
        role = b.get("instruction", "")
        focus = _AGENT_FOCUS.get(key, "ilgili göstergeler")
        blocks.append(
            f"### AJAN: {name}\n"
            f"- Rolün / Bakış açın: {role}\n"
            f"- Analiz odağın: {focus}"
        )
    return "\n\n".join(blocks)


def _build_directive_block():
    try:
        from src import ai_brains
        directive = ai_brains.load_directive()
        if directive:
            return (
                "\n\n### KULLANICININ EĞİTİM TALİMATI (AI Yönet üzerinden verildi)\n"
                f"{directive}\nBu talimatı tüm beyinler için ÜSTTEN BAĞLAYICI bir rehber olarak uygula."
            )
    except Exception:
        pass
    return ""


def _build_reflection_block():
    """Son işlemlerin net K/Z özeti -> 'otonom öğrenme logları' olarak beslenir."""
    try:
        from src import self_improve
        refl = self_improve.build_recent_reflection(5)
        if refl:
            return (
                "\n\n### SON İŞLEMLERİN OTONOM ÖĞRENME LOGLARI (Son 5 işlem)\n"
                f"{refl}\n"
                "Bu logdaki bilgi, GÜVEN SKORU kuralının '+0.30 geçmiş hatalardan kaçınma' "
                "kısmını besler. Beyinler bu hataları tekrarlamamalıdır."
            )
    except Exception:
        pass
    return ""


def _build_lessons_block(lessons):
    if not lessons:
        return ""
    try:
        lines = []
        for les in lessons[-6:]:
            ls = les.get("lesson", "") if isinstance(les, dict) else str(les)
            if ls:
                lines.append(f"- {ls}")
        if not lines:
            return ""
        return (
            "\n\n### SİSTEMİN ÖĞRENDİĞİ DERSLER (geçmiş işlemlerden)\n"
            + "\n".join(lines)
            + "\nBu dersleri dikkate al: başarısız yaklaşımlardan kaçın, işe yarayanı güçlendir."
        )
    except Exception:
        return ""


_SYSTEM_PROMPT = """Sen, 5 farklı yapay zeka ajanından oluşan otonom bir BTC Alım-Satım Konsensüs Sistemi'nin koordinatörüsün. Aşağıdaki 5 ajanın her biri kendi uzmanlık alanına göre filtreleme yapar ve diğer ajanlarla rasyonel bir tartışma yürütür. Her ajan için tanımlı rolü kullanarak o ajanın bakış açısından düşün ve çıktıyı üret.

## 5 AJANIN ROLLERİ VE ODAKLARI
{AGENT_PERSONAS}

KESİN YASAKLAR VE KURALLAR:
1. Finansal klişeler ("Piyasa belirsiz duruyor", "Yatırım tavsiyesi değildir") KESİNLİKLE kullanma. Net, analitik ve agresif ol.
2. Diğer ajanların kararlarına körü körüne katılma (Groupthink yapma). Eğer masadaki diğer ajanlar "AL" diyorsa ve senin indikatörün bunu desteklemiyorsa, konsensüsü bozma pahasına "BEKLE" kararı ver ve gerekçeni matematiksel olarak masaya koy.
3. Çıktı formatını bozma. Sadece ham analizini, nihai kararını (AL / SAT / BEKLE) ve güven skorunu üret.

GÜVEN SKORU HESAPLAMA METRİĞİ (0.00 - 1.00):
Güven skorunu rastgele belirleme, şu kurallara göre puan ver:
- Fiyat aksiyonu senin indikatör setinle %100 uyumluysa: +0.40
- Masadaki muhalif/karamsar ajanın argümanını çürütebiliyorsan: +0.30
- Son 5 işlemdeki otonom öğrenme loglarında belirtilen geçmiş hatalardan kaçınabiliyorsan: +0.30
Toplam skor 0.70'in altındaysa kararın ne olursa olsun ağırlığın "BEKLE" yönünde olacaktır.
{REFLECTION}
{DIRECTIVE}
{LESSONS}

{CONTEXT}

Yukarıdaki verileri analiz et ve 5 uzman beynin tartışmasını simüle et. SADECE aşağıdaki JSON formatında cevap ver:

{
  "brains": [
    {"ajan": "TREND", "analiz": "Kısa, net ve verilere dayalı argüman (Maksimum 2 cümle)", "karar": "AL", "guven_skoru": 0.82},
    {"ajan": "VOLATILITE", "analiz": "...", "karar": "BEKLE", "guven_skoru": 0.55},
    {"ajan": "HACIM", "analiz": "...", "karar": "AL", "guven_skoru": 0.71},
    {"ajan": "SEVİYE", "analiz": "...", "karar": "SAT", "guven_skoru": 0.60},
    {"ajan": "DUYGU", "analiz": "...", "karar": "BEKLE", "guven_skoru": 0.50}
  ],
  "final_decision": "AL",
  "final_confidence": 0.70,
  "summary": "1-2 cümle genel değerlendirme"
}"""


_KARAR_MAP = {"AL": "BUY", "BUY": "BUY", "SAT": "SELL", "SELL": "SELL",
              "BEKLE": "HOLD", "HOLD": "HOLD", "WAIT": "HOLD"}


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

    if haberler and len(haberler) > 0:
        ctx += "\n### SON HABERLER\n"
        for h in haberler[:5]:
            baslik = h.get("baslik", "")
            sentiment = h.get("sentiment", "notr")
            ctx += f"- [{sentiment.upper()}] {baslik}\n"

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

    personas = _build_agent_personas(brains)
    reflection = _build_reflection_block()
    directive = _build_directive_block()
    lessons_text = _build_lessons_block(lessons)

    try:
        prompt = _SYSTEM_PROMPT
        prompt = prompt.replace("{AGENT_PERSONAS}", personas)
        prompt = prompt.replace("{REFLECTION}", reflection)
        prompt = prompt.replace("{DIRECTIVE}", directive)
        prompt = prompt.replace("{LESSONS}", lessons_text)
        prompt = prompt.replace("{CONTEXT}", context)

        response = model.generate_content(prompt)
        text = response.text.strip()

        # JSON parse
        debate = json.loads(text)

        raw_brains = debate.get("brains", [])
        if not isinstance(raw_brains, list) or len(raw_brains) < 1:
            print("[GEMINI] Gecersiz cikti: brains yok/hatali")
            return _LAST_DEBATE

        # Ham beyinleri dahili formata map et (karar AL/SAT/BEKLE -> BUY/SELL/HOLD)
        mapped = []
        for bb in raw_brains:
            karar = str(bb.get("karar", "BEKLE")).strip().upper()
            vote = _KARAR_MAP.get(karar, "HOLD")
            try:
                conf = float(bb.get("guven_skoru", bb.get("confidence", 0)) or 0)
            except Exception:
                conf = 0.0
            mapped.append({
                "name": bb.get("ajan", bb.get("name", "?")),
                "ajan": bb.get("ajan", bb.get("name", "?")),
                "vote": vote,
                "karar": karar,
                "confidence": round(conf, 3),
                "guven_skoru": round(conf, 3),
                "argument": bb.get("analiz", bb.get("argument", "")),
                "analiz": bb.get("analiz", bb.get("argument", "")),
            })
        debate["brains"] = mapped

        # Meta veriler ekle
        debate["timestamp"] = datetime.now().isoformat()
        debate["symbol"] = settings.symbol
        debate["price"] = teknik.get("price", 0)

        # final_decision map
        fd_raw = str(debate.get("final_decision", "")).strip().upper()
        debate["final_decision"] = _KARAR_MAP.get(fd_raw, "HOLD")

        # Oy sayımı
        buy_count = sum(1 for b in mapped if b["vote"] == "BUY")
        sell_count = sum(1 for b in mapped if b["vote"] == "SELL")
        hold_count = sum(1 for b in mapped if b["vote"] == "HOLD")
        debate["buy_count"] = buy_count
        debate["sell_count"] = sell_count
        debate["hold_count"] = hold_count

        _LAST_DEBATE = debate
        _LAST_DEBATE_TIME = now

        fd = debate.get("final_decision", "HOLD")
        fc = debate.get("final_confidence", 0)
        print(f"[GEMINI] Debate tamamlandi: {fd} (%{float(fc)*100:.0f}) | AL:{buy_count} SAT:{sell_count} BEKLE:{hold_count}")
        for b in mapped:
            print(f"  [{b['name']}] {b['karar']} (%{b['guven_skoru']*100:.0f}): {str(b['analiz'])[:80]}")

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
