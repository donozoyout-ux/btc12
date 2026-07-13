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
    "trend": "EMA/MACD uyumu, trend yönü ve momentum avcılığı",
    "volatility": "RSI, StochRSI ve Bollinger Band matematiği; aşırı alım/satım bölgeleri",
    "volume": "Hacim oranı, orderbook (bid/ask) dengesi ve balina akışı",
    "level": "Destek/direnç seviyeleri, kırılım sinyalleri ve risk yönetimi (stop-loss)",
    "sentiment": "Haber/duygu tonu, Fear & Greed endeksi ve hakemlik (nihai denge)",
}

# Kullanıcının tanımladığı 5 ajans rol matrisi
_AGENT_ROLES = {
    "trend": "Trend Avcısı",
    "volatility": "Matematikçi",
    "volume": "Balina İzleyici",
    "level": "Risk Yöneticisi",
    "sentiment": "Hakem",
}

_ORDER = ["trend", "volatility", "volume", "level", "sentiment"]

# Rol adı -> dahili anahtar (çıktı ayrıştırma için)
_ROLE_TO_KEY = {v: k for k, v in _AGENT_ROLES.items()}

# ---------------------------------------------------------------------------
#  ROL MATRİSİ + DİNAMİK İNDİKATÖR DAĞILIMI
#  Backend döngüsünden gelen ham indikatör verisi (RSI, MACD, EMA, ...)
#  buraya göre her rolün prompt'una YALNIZCA kendi uzmanlık alanıyla
#  ilgili göstergeler olarak dağıtılır. Böylece ajanlar birbirinin
#  verisini kopyalamaz, sürü psikolojisi (groupthink) kırılır.
# ---------------------------------------------------------------------------
ROLE_MATRIX = {
    "trend": {  # Trend Avcısı -> EMA / MACD / momentum
        "indicators": ["price", "ema8", "ema21", "ema_cross", "ema_dist",
                       "macd_line", "macd_hist", "macd_hist_prev", "sling_color",
                       "sling_dist", "momentum_score", "price_change_5", "adx",
                       "di_plus", "di_minus", "donchian_pos"],
    },
    "volatility": {  # Matematikçi -> RSI / StochRSI / Bollinger matematiği
        "indicators": ["price", "rsi", "rsi_prev", "stoch_rsi", "stoch_rsi_prev",
                       "bb_pct", "bb_upper", "bb_lower", "atr", "atr_pct",
                       "cci", "williams_r", "mfi"],
    },
    "volume": {  # Balina İzleyici -> hacim / orderbook / balina akışı
        "indicators": ["price", "vol_ratio", "mfi", "obv_signal", "vwap_dist",
                       "orderbook", "price_change_5"],
    },
    "level": {  # Risk Yöneticisi -> destek/direnç / kırılım / stop-loss
        "indicators": ["price", "support", "resistance", "breakout_up", "breakout_down",
                       "bb_upper", "bb_lower", "atr", "atr_pct", "donchian_high",
                       "donchian_low", "sling_color"],
    },
    "sentiment": {  # Hakem -> haber/duygu + genel dengenin sağlanması
        "indicators": ["price", "rsi", "ema_cross", "macd_hist", "vol_ratio"],
        "news": True,
    },
}

# Ham indikatör anahtarı -> arayüzdeki Türkçe etiket
_INDICATOR_LABELS = {
    "price": "Fiyat", "ema8": "EMA 8", "ema21": "EMA 21", "ema_cross": "EMA Kesişim",
    "ema_dist": "EMA Mesafesi (%)", "macd_line": "MACD Çizgisi", "macd_hist": "MACD Histogram",
    "macd_hist_prev": "MACD Histogram (önceki)", "sling_color": "Sling Shot Rengi",
    "sling_dist": "Sling Mesafe (%)", "momentum_score": "Momentum Skoru", "price_change_5": "5-Bar Fiyat Değişimi (%)",
    "adx": "ADX", "di_plus": "DI+", "di_minus": "DI-", "donchian_pos": "Donchian Pozisyon",
    "rsi": "RSI (14)", "rsi_prev": "RSI (önceki)", "stoch_rsi": "StochRSI", "stoch_rsi_prev": "StochRSI (önceki)",
    "bb_pct": "Bollinger %B", "bb_upper": "BB Üst", "bb_lower": "BB Alt", "atr": "ATR", "atr_pct": "ATR (%)",
    "cci": "CCI", "williams_r": "Williams %R", "mfi": "MFI", "vol_ratio": "Hacim Oranı",
    "obv_signal": "OBV Sinyali", "vwap_dist": "VWAP Mesafe (%)", "support": "Destek",
    "resistance": "Direnç", "breakout_up": "Yukarı Kırılım", "breakout_down": "Aşağı Kırılım",
    "donchian_high": "Donchian Yüksek", "donchian_low": "Donchian Düşük",
}


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
        role = _AGENT_ROLES.get(key, b.get("label", key).upper())
        instruction = b.get("instruction", "")
        focus = _AGENT_FOCUS.get(key, "ilgili göstergeler")
        info = ROLE_MATRIX.get(key, {})
        assigned = ", ".join(
            _INDICATOR_LABELS.get(i, i) for i in info.get("indicators", [])
        )
        if info.get("news"):
            assigned += (", HABERLER" if assigned else "HABERLER")
        blocks.append(
            f"### AJAN: {role}\n"
            f"- Rolün / Bakış açın: {instruction}\n"
            f"- Analiz odağın: {focus}\n"
            f"- Sana atanan göstergeler (yalnızca bunları kullan): {assigned}"
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
    {"ajan": "Trend Avcısı", "analiz": "Kısa, net ve verilere dayalı argüman (MAKSİMUM 2 CÜMLE)", "karar": "AL", "guven_skoru": 0.82},
    {"ajan": "Matematikçi", "analiz": "...", "karar": "BEKLE", "guven_skoru": 0.55},
    {"ajan": "Balina İzleyici", "analiz": "...", "karar": "AL", "guven_skoru": 0.71},
    {"ajan": "Risk Yöneticisi", "analiz": "...", "karar": "SAT", "guven_skoru": 0.60},
    {"ajan": "Hakem", "analiz": "...", "karar": "BEKLE", "guven_skoru": 0.50}
  ],
  "final_decision": "AL",
  "final_confidence": 0.70,
  "summary": "1-2 cümle genel değerlendirme"
}

ÇIKTI KURALLARI (KESİN):
- "brains" dizisinde TAM OLARAK 5 nesne olmalı; her birinin "ajan" alanı yukarıdaki rollerle birebir aynı olmalı: "Trend Avcısı", "Matematikçi", "Balina İzleyici", "Risk Yöneticisi", "Hakem".
- "analiz": SADECE o role atanan göstergelere dayalı, maksimum 2 cümlelik veri argümanı.
- "karar": yalnızca "AL", "SAT" veya "BEKLE" değerlerinden biri.
- "guven_skoru": 0.00 - 1.00 arası sayısal değer.
- Diğer ajanların kararını körü körüne tekrarlama; eğer verin desteklemiyorsa "BEKLE" de.
"""


_KARAR_MAP = {"AL": "BUY", "BUY": "BUY", "SAT": "SELL", "SELL": "SELL",
              "BEKLE": "HOLD", "HOLD": "HOLD", "WAIT": "HOLD"}


def _build_market_context(teknik, haberler=None, ml_votes=None):
    """Piyasa verilerini rol matrisine göre HER AJANA YALNIZCA kendi
    uzmanlık göstergelerini içeren bloklar halinde dağıtır.

    Dönen metin doğrudan {CONTEXT} yerine basılır; böylece Trend Avcısı
    yalnızca EMA/MACD, Matematikçi yalnızca RSI/Bollinger, Balina İzleyici
    yalnızca hacim/orderbook, Risk Yöneticisi yalnızca destek/direnç,
    Hakem ise haberler + genel dengede görür. Bu, ajanların birbirinin
    ham verisini kopyalayıp sürü psikolojisine girmesini engeller.
    """
    if not teknik or "price" not in teknik:
        return None

    blocks = []
    for key in _ORDER:
        info = ROLE_MATRIX.get(key, {})
        role = _AGENT_ROLES.get(key, key)
        focus = _AGENT_FOCUS.get(key, "ilgili göstergeler")

        lines = [
            f"## {role.upper()} — ATANAN VERİ",
            f"(Bu role yalnızca aşağıdaki göstergeler verildi; analiz odağı: {focus})",
        ]
        for ind in info.get("indicators", []):
            if ind == "orderbook":
                ob = teknik.get("orderbook", {}) or {}
                lines.append(f"- Orderbook Bid/Ask Oranı: {ob.get('bid_ask_ratio', 1.0)}")
                lines.append(f"- Orderbook Sinyalı: {ob.get('bid_ask_sinyal', 'notr')}")
                lines.append(f"- Spread: {ob.get('spread', 0)}")
                continue
            val = teknik.get(ind)
            if val is None:
                continue
            if isinstance(val, bool):
                val = "EVET" if val else "Hayır"
            elif isinstance(val, float):
                val = round(val, 3)
            label = _INDICATOR_LABELS.get(ind, ind)
            lines.append(f"- {label}: {val}")

        if info.get("news") and haberler and len(haberler) > 0:
            lines.append("- SON HABERLER (duygu/ton):")
            for h in haberler[:5]:
                baslik = h.get("baslik", h.get("title", ""))
                sentiment = h.get("sentiment", "notr")
                lines.append(f"  * [{str(sentiment).upper()}] {baslik}")

        blocks.append("\n".join(lines))

    ctx = "\n\n".join(blocks)

    if ml_votes:
        ctx += "\n\n### ML AJAN OYLAMASI (Mevcut Sistem)\n"
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
            # "ajan" alanı ya rol adı ya dahili anahtar olabilir; ikisine de normalize et
            raw_name = str(bb.get("ajan", bb.get("name", ""))).strip()
            internal_key = _ROLE_TO_KEY.get(raw_name)
            if not internal_key:
                internal_key = raw_name.lower()
            ajan_display = _AGENT_ROLES.get(internal_key, raw_name)
            analiz = bb.get("analiz", bb.get("argument", ""))
            # Analizi 2 cümleyle sınırla (noktaya göre böl, ilk 2 cümle)
            if analiz and isinstance(analiz, str):
                parts = [p.strip() for p in analiz.replace("!", ".").split(". ") if p.strip()]
                if len(parts) > 2:
                    analiz = parts[0] + ". " + parts[1] + "."
            mapped.append({
                "name": internal_key,
                "ajan": ajan_display,
                "vote": vote,
                "karar": karar,
                "confidence": round(conf, 3),
                "guven_skoru": round(conf, 3),
                "argument": analiz,
                "analiz": analiz,
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
