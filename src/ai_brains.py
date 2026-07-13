"""
5 Analiz Bölümü için Düzenlenebilir AI Beyin Sistemi
====================================================
Her analiz bölümüne (trend, volatilite, hacim, seviye, duygu) özel bir
"beyin" talimatı (instruction) atanır. Kullanıcı bu talimatları panelden
düzenleyip kaydedebilir. Gemini 5-Brain tartışması bu talimatları kullanır.
"""

import json
import os

BRAIN_FILE = os.path.join("config", "ai_brains.json")

DEFAULT_BRAINS = {
    "trend": {
        "label": "Trend & Momentum",
        "icon": "📈",
        "color": "from-blue-600 to-cyan-500",
        "enabled": True,
        "instruction": (
            "Sen bir TREND & MOMENTUM stratejistisin. EMA kesisimleri, MACD momentumu ve "
            "fiyat trendlerine odaklanirsin. Net bir yükselen trend oldugunda trendi takip "
            "ederek yükselisten faydalanirsin (AL); düsen trendlerde SAT sinyali verirsin. "
            "Sistem tamamen katı (sabit) degil: trend varsa o trendi izler ve artistan "
            "yararlanirsin. Trendi asla karsi yonde yakalama; kirilimlari tedbirli teyit et. "
            "Risk disiplini her zaman ön planda, ama firsatlari da kacirma."
        ),
    },
    "volatility": {
        "label": "Volatilite & RSI",
        "icon": "📊",
        "color": "from-amber-500 to-orange-500",
        "enabled": True,
        "instruction": (
            "Sen bir VOLATILITE & MEAN REVERSION analistisin. RSI asiri alim/satim bolgeleri, "
            "StochRSI ve Bollinger Band pozisyonuna odaklanirsin. Asiri satimda AL, asiri "
            "alimda SAT sinyali verirsin. Volatiliteyi disiplinli yönet; stop-loss'u makul "
            "tut, gereksiz risk almamaya özen göster. Hedefin günlük sabit getiri degil, "
            "her islemde riski kontrol altinda tutmaktir."
        ),
    },
    "volume": {
        "label": "Hacim & Orderbook",
        "icon": "📦",
        "color": "from-emerald-500 to-green-500",
        "enabled": True,
        "instruction": (
            "Sen bir HACIM & ORDERBOOK uzmanisin. Alim/satim hacim orani, orderbook "
            "dengessizligi (bid/ask ratio) ve hacimle teyit edilen hareketlere odaklanirsin. "
            "Alis baskisinda AL, satis baskisinda SAT sinyali verirsin. Gercek hacimle "
            "desteklenmeyen hareketlere guvenme; anlik olaylari tedbirli degerlendir ve "
            "asisiri islemden kacin."
        ),
    },
    "level": {
        "label": "Kirilim & Seviye",
        "icon": "🎯",
        "color": "from-rose-500 to-pink-500",
        "enabled": True,
        "instruction": (
            "Sen bir DESTEK/DIRENC & KIRILIM mimarin. Fiyatin destek ve direnc "
            "seviyelerine gore konumunu, kirilim sinyallerini ve Bollinger Band sinirlarini "
            "analiz edersin. Yukari kirilimda AL, asagi kirilimda SAT sinyali verirsin. "
            "Kirilimlari sabirla dogrula; yanlis sinyallerden kacinmak icin onay beklet."
        ),
    },
    "sentiment": {
        "label": "Duygu & Haber",
        "icon": "🧠",
        "color": "from-purple-500 to-violet-500",
        "enabled": True,
        "instruction": (
            "Sen bir MAKRO DUYGU & HABER analistisin. Son haberlerin duygusal tonunu, "
            "Fear & Greed endeksini ve piyasa psikolojisini degerlendirirsin. Anlik olaylari "
            "(haber, tweet, makro gelisme) tedbirli bir sekilde degerlendir ve fiyata "
            "etkisini tahmin et. Contrarian (karsit) bakis acisi sunarsin; pozitif duygu "
            "asiriysa temkinli olur, panik satislarinda firsat ararsin. Risk yonetimini "
            "her zaman on planda tut, asiri iyimserlige kapilma."
        ),
    },
}

_ORDER = ["trend", "volatility", "volume", "level", "sentiment"]


def _ensure_file():
    path = os.path.join("config", "ai_brains.json")
    if not os.path.exists("config"):
        os.makedirs("config", exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_BRAINS, f, ensure_ascii=False, indent=2)
        return DEFAULT_BRAINS
    return None


def load_brains():
    _ensure_file()
    try:
        with open(BRAIN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    # Eksik beyinleri varsayilanlarla tamamla
    merged = {}
    for key in _ORDER:
        if key in data:
            merged[key] = {**DEFAULT_BRAINS[key], **data[key]}
        else:
            merged[key] = dict(DEFAULT_BRAINS[key])
    return merged


def save_brains(brains):
    if not os.path.exists("config"):
        os.makedirs("config", exist_ok=True)
    with open(BRAIN_FILE, "w", encoding="utf-8") as f:
        json.dump(brains, f, ensure_ascii=False, indent=2)
    return True


def update_brain(key, instruction=None, enabled=None, label=None):
    brains = load_brains()
    if key not in brains:
        return None
    if instruction is not None:
        brains[key]["instruction"] = instruction
    if enabled is not None:
        brains[key]["enabled"] = bool(enabled)
    if label is not None:
        brains[key]["label"] = label
    save_brains(brains)
    return brains[key]


def order():
    return list(_ORDER)
