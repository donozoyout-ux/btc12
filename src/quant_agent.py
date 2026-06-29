import json
import os
import numpy as np
from datetime import datetime
from src.config import settings


class QuantAgent:
    def __init__(self):
        self.state_file = settings.memory_file
        self.state = self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except:
                pass
        return {
            "son_islem_kar_zarar": 0.0,
            "son_hatalar": [],
            "aktif_strateji_notu": "",
            "risk_seviyesi_ayari": "normal",
            "ardisik_kayip": 0,
            "son_sinyal": None,
            "toplam_islem": 0,
            "kazanma": 0,
            "kaybetme": 0,
        }

    def _save_state(self):
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2, default=str)

    def analyze(self, teknik_analiz, internet_ve_haberler, mevcut_portfoy, gecmis_hafiza):
        hata_var = False
        system_log = ""

        if teknik_analiz is None or "price" not in teknik_analiz:
            system_log = "HATA: Teknik analiz verisi eksik"
            return self._hold_karar("normal", "", system_log)

        fiyat = teknik_analiz["price"]
        rsi = teknik_analiz["rsi"]
        ema_cross = teknik_analiz["ema_cross"]
        macd_hist = teknik_analiz["macd_hist"]
        macd_hist_prev = teknik_analiz["macd_hist_prev"]
        vol_ratio = teknik_analiz["vol_ratio"]
        bb_pct = teknik_analiz["bb_pct"]
        atr = teknik_analiz["atr"]

        acik_pozisyon = mevcut_portfoy.get("acik_pozisyon", False)
        giris_fiyati = mevcut_portfoy.get("giris_fiyati", 0)
        usdt_bakiye = mevcut_portfoy.get("usdt_bakiye", 0)
        btc_bakiye = mevcut_portfoy.get("btc_bakiye", 0)

        ardisik_kayip = self.state.get("ardisik_kayip", 0)
        risk_seviyesi = self.state.get("risk_seviyesi_ayari", "normal")

        min_confidence = 0.4
        if ardisik_kayip >= settings.max_consecutive_losses:
            min_confidence = 0.6
            risk_seviyesi = "muhafazakar"

        buy_score = 0.0
        sell_score = 0.0
        reasons = []
        direction = "HOLD"

        if rsi < 30:
            buy_score += 0.35
            reasons.append(f"RSI asiri satim ({rsi})")
        elif rsi < 40:
            buy_score += 0.15
            reasons.append(f"RSI dusuk ({rsi})")
        elif rsi > 70:
            sell_score += 0.35
            reasons.append(f"RSI asiri alim ({rsi})")
        elif rsi > 60:
            sell_score += 0.15

        if macd_hist > 0 and macd_hist_prev <= 0:
            buy_score += 0.25
            reasons.append("MACD pozitif kesişim")
        elif macd_hist > 0 and macd_hist > macd_hist_prev:
            buy_score += 0.1
        elif macd_hist < 0 and macd_hist_prev >= 0:
            sell_score += 0.25
            reasons.append("MACD negatif kesişim")
        elif macd_hist < 0 and macd_hist < macd_hist_prev:
            sell_score += 0.1

        if ema_cross == "bullish":
            buy_score += 0.15
        else:
            sell_score += 0.15

        if bb_pct < 0:
            buy_score += 0.15
            reasons.append("BB alt bandinda")
        elif bb_pct > 1:
            sell_score += 0.15
            reasons.append("BB ust bandinda")

        if vol_ratio > 1.5 and buy_score > sell_score:
            buy_score += 0.1
            reasons.append(f"Hacim destekli ({vol_ratio}x)")
        elif vol_ratio > 1.5 and sell_score > buy_score:
            sell_score += 0.1
            reasons.append(f"Hacim destekli ({vol_ratio}x)")

        haber_sentiment = 0.0
        for haber in internet_ve_haberler:
            if haber.get("sentiment") == "pozitif":
                haber_sentiment += 0.05
            elif haber.get("sentiment") == "negatif":
                haber_sentiment -= 0.05

        if haber_sentiment > 0:
            buy_score += haber_sentiment
        elif haber_sentiment < 0:
            sell_score += abs(haber_sentiment)

        if not acik_pozisyon:
            if buy_score > sell_score and buy_score >= min_confidence:
                direction = "BUY"
                confidence = min(buy_score, 1.0)

                sl_price = round(fiyat - 1.5 * atr, 2)
                tp_price = round(fiyat + 3 * atr, 2)

                portfolio_value = usdt_bakiye + (btc_bakiye * fiyat)
                risk_amount = portfolio_value * (settings.risk_per_trade / 100)
                risk_per_unit = abs(fiyat - sl_price)
                size_pct = round((risk_amount / risk_per_unit * fiyat) / portfolio_value * 100, 2) if risk_per_unit > 0 and portfolio_value > 0 else 0
                size_pct = min(max(size_pct, 1), 95)

                self.state["son_sinyal"] = {
                    "action": "BUY",
                    "price": fiyat,
                    "time": datetime.now().isoformat()
                }

                memory_update = {
                    "aktif_strateji_notu": f"ALIS: {', '.join(reasons[:2])}",
                    "risk_seviyesi_ayari": risk_seviyesi
                }

                return {
                    "action": "BUY",
                    "confidence_score": round(confidence, 2),
                    "execution": {
                        "size_percentage": size_pct,
                        "stop_loss": sl_price,
                        "take_profit": tp_price,
                    },
                    "memory_update": memory_update,
                    "system_log": system_log
                }

        else:
            if sell_score > buy_score and sell_score >= min_confidence:
                direction = "SELL"
                confidence = min(sell_score, 1.0)

                mevcut_kar = (fiyat - giris_fiyati) / giris_fiyati * 100 if giris_fiyati > 0 else 0

                self.state["son_sinyal"] = {
                    "action": "SELL",
                    "price": fiyat,
                    "time": datetime.now().isoformat()
                }

                memory_update = {
                    "aktif_strateji_notu": f"SATIS: {', '.join(reasons[:2])} (Kar: %{mevcut_kar:+.2f})" if abs(mevcut_kar) > 0 else f"SATIS: {', '.join(reasons[:2])}",
                    "risk_seviyesi_ayari": risk_seviyesi
                }

                return {
                    "action": "SELL",
                    "confidence_score": round(confidence, 2),
                    "execution": {
                        "size_percentage": 100,
                        "stop_loss": 0,
                        "take_profit": 0,
                    },
                    "memory_update": memory_update,
                    "system_log": system_log
                }

        return self._hold_karar(risk_seviyesi, "Net sinyal yok", system_log)

    def _hold_karar(self, risk_seviyesi, strateji_notu, system_log=""):
        return {
            "action": "HOLD",
            "confidence_score": 0.0,
            "execution": {
                "size_percentage": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
            },
            "memory_update": {
                "aktif_strateji_notu": strateji_notu,
                "risk_seviyesi_ayari": risk_seviyesi,
            },
            "system_log": system_log
        }

    def islem_sonucu_kaydet(self, kar_zarar):
        self.state["toplam_islem"] += 1
        if kar_zarar > 0:
            self.state["kazanma"] += 1
            self.state["ardisik_kayip"] = 0
        elif kar_zarar < 0:
            self.state["kaybetme"] += 1
            self.state["ardisik_kayip"] += 1
        self.state["son_islem_kar_zarar"] = round(kar_zarar, 4)
        self._save_state()

    def get_state(self):
        return self.state


quant_agent = QuantAgent()
