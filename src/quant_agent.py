import json
import os
import numpy as np
from datetime import datetime
from src.config import settings
from src.ai_model import ai_model
from src.strategy import signal_strategy


class QuantAgent:
    def __init__(self):
        self.state_file = settings.memory_file
        self.state = self._load_state()
        self._trade_history = []

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
            "weights": {
                "rsi": 1.0, "macd": 1.0, "ema": 1.0,
                "bb": 1.0, "vol": 1.0, "breakout": 1.0,
                "orderbook": 1.0, "haber": 1.0, "momentum": 1.0
            },
            "weight_hits": {k: 0 for k in ["rsi","macd","ema","bb","vol","breakout","orderbook","haber","momentum"]},
            "weight_misses": {k: 0 for k in ["rsi","macd","ema","bb","vol","breakout","orderbook","haber","momentum"]},
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
        ema_dist = teknik_analiz.get("ema_dist", 0)
        macd_hist = teknik_analiz["macd_hist"]
        macd_hist_prev = teknik_analiz["macd_hist_prev"]
        vol_ratio = teknik_analiz["vol_ratio"]
        bb_pct = teknik_analiz["bb_pct"]
        atr = teknik_analiz["atr"]
        breakout_up = teknik_analiz.get("breakout_up", 0)
        breakout_down = teknik_analiz.get("breakout_down", 0)
        price_change_5 = teknik_analiz.get("price_change_5", 0)

        ob = teknik_analiz.get("orderbook", {})
        ob_sinyal = ob.get("bid_ask_sinyal", "notr")
        ob_ratio = ob.get("bid_ask_ratio", 1.0)

        acik_pozisyon = mevcut_portfoy.get("acik_pozisyon", False)
        giris_fiyati = mevcut_portfoy.get("giris_fiyati", 0)
        usdt_bakiye = mevcut_portfoy.get("usdt_bakiye", 0)
        btc_bakiye = mevcut_portfoy.get("btc_bakiye", 0)

        ardisik_kayip = self.state.get("ardisik_kayip", 0)
        risk_seviyesi = self.state.get("risk_seviyesi_ayari", "normal")
        w = self.state.get("weights", {k: 1.0 for k in ["rsi","macd","ema","bb","vol","breakout","orderbook","haber","momentum"]})

        ai_prob, ai_conf = ai_model.predict(teknik_analiz)

        signal = signal_strategy.analyze(teknik_analiz)
        if signal.get("strict_signal") and signal["action"] in ("BUY", "SELL"):
            if signal["action"] == "BUY" and ai_prob >= 0.4 and not acik_pozisyon:
                self.state["son_sinyal"] = {"action": "BUY", "source": "STRICT", "ai_prob": ai_prob}
                self._save_state()
                return {
                    "action": "BUY",
                    "confidence_score": round(max(ai_prob, 0.7), 2),
                    "execution": {
                        "size_percentage": 95,
                        "stop_loss": signal.get("stop_loss", 0),
                        "take_profit": signal.get("target_profit", 0),
                    },
                    "memory_update": {
                        "aktif_strateji_notu": signal["reason"],
                        "risk_seviyesi_ayari": risk_seviyesi,
                    },
                    "system_log": f"STRICT+AI:{ai_prob:.0%}"
                }
            if signal["action"] == "SELL" and ai_prob <= 0.6 and acik_pozisyon:
                self.state["son_sinyal"] = {"action": "SELL", "source": "STRICT", "ai_prob": ai_prob}
                self._save_state()
                return {
                    "action": "SELL",
                    "confidence_score": round(max(1 - ai_prob, 0.7), 2),
                    "execution": {
                        "size_percentage": 100,
                        "stop_loss": 0,
                        "take_profit": 0,
                    },
                    "memory_update": {
                        "aktif_strateji_notu": signal["reason"],
                        "risk_seviyesi_ayari": risk_seviyesi,
                    },
                    "system_log": f"STRICT+AI:{ai_prob:.0%}"
                }
        min_confidence = 0.10
        if ardisik_kayip >= settings.max_consecutive_losses:
            min_confidence = 0.35
            risk_seviyesi = "muhafazakar"

        buy_score = 0.0
        sell_score = 0.0
        reasons = []
        used_indicators = []
        direction = "HOLD"

        rsi_w = w.get("rsi", 1.0)
        macd_w = w.get("macd", 1.0)
        ema_w = w.get("ema", 1.0)
        bb_w = w.get("bb", 1.0)
        vol_w = w.get("vol", 1.0)
        breakout_w = w.get("breakout", 1.0)
        ob_w = w.get("orderbook", 1.0)
        momentum_w = w.get("momentum", 1.0)

        if rsi < 30:
            buy_score += 0.35 * rsi_w
            reasons.append(f"RSI asiri satim ({rsi})")
            used_indicators.append("rsi")
        elif rsi < 35:
            buy_score += 0.20 * rsi_w
            reasons.append(f"RSI dusuk ({rsi})")
            used_indicators.append("rsi")
        elif rsi < 42:
            buy_score += 0.10 * rsi_w
        elif rsi > 70:
            sell_score += 0.35 * rsi_w
            reasons.append(f"RSI asiri alim ({rsi})")
            used_indicators.append("rsi")
        elif rsi > 65:
            sell_score += 0.20 * rsi_w
            reasons.append(f"RSI yuksek ({rsi})")
            used_indicators.append("rsi")
        elif rsi > 58:
            sell_score += 0.10 * rsi_w

        macd_improving = (macd_hist > macd_hist_prev)
        macd_worsening = (macd_hist < macd_hist_prev)

        if macd_hist > 0 and macd_hist_prev <= 0:
            buy_score += 0.25 * macd_w
            reasons.append("MACD pozitif kesisim")
            used_indicators.append("macd")
        elif macd_hist > 0 and macd_improving:
            buy_score += 0.15 * macd_w
            reasons.append("MACD gucleniyor")
            used_indicators.append("macd")
        elif macd_hist < 0 and macd_improving:
            buy_score += 0.10 * macd_w
            reasons.append("MACD toparliyor")
            used_indicators.append("macd")
        elif macd_hist < 0 and macd_hist_prev >= 0:
            sell_score += 0.25 * macd_w
            reasons.append("MACD negatif kesisim")
            used_indicators.append("macd")
        elif macd_hist < 0 and macd_worsening:
            sell_score += 0.15 * macd_w
            reasons.append("MACD zayifliyor")
            used_indicators.append("macd")
        elif macd_hist > 0 and macd_worsening:
            sell_score += 0.10 * macd_w

        if ema_cross == "bullish":
            buy_score += 0.15 * ema_w
        else:
            sell_score += 0.15 * ema_w
        used_indicators.append("ema")

        if bb_pct < 0.1:
            buy_score += 0.15 * bb_w
            reasons.append("BB alt banda yakin")
            used_indicators.append("bb")
        elif bb_pct < 0:
            buy_score += 0.20 * bb_w
            reasons.append("BB alt bandinda")
            used_indicators.append("bb")
        elif bb_pct > 0.9:
            sell_score += 0.15 * bb_w
            reasons.append("BB ust banda yakin")
            used_indicators.append("bb")
        elif bb_pct > 1:
            sell_score += 0.20 * bb_w
            reasons.append("BB ust bandinda")
            used_indicators.append("bb")

        if vol_ratio > 2.0 and buy_score > sell_score:
            buy_score += 0.15 * vol_w
            reasons.append(f"Hacim cok yuksek ({vol_ratio}x)")
            used_indicators.append("vol")
        elif vol_ratio > 1.5 and buy_score > sell_score:
            buy_score += 0.10 * vol_w
            reasons.append(f"Hacim destekli ({vol_ratio}x)")
            used_indicators.append("vol")
        elif vol_ratio > 2.0 and sell_score > buy_score:
            sell_score += 0.15 * vol_w
            reasons.append(f"Hacim cok yuksek ({vol_ratio}x)")
            used_indicators.append("vol")
        elif vol_ratio > 1.5 and sell_score > buy_score:
            sell_score += 0.10 * vol_w
            reasons.append(f"Hacim destekli ({vol_ratio}x)")
            used_indicators.append("vol")

        if breakout_up > 0:
            buy_score += 0.30 * breakout_w
            reasons.append("Yukari breakout")
            used_indicators.append("breakout")
        if breakout_down > 0:
            sell_score += 0.30 * breakout_w
            reasons.append("Asagi breakout")
            used_indicators.append("breakout")

        if -2.0 < ema_dist < 0 and ema_cross == "bullish":
            buy_score += 0.20 * ema_w
            reasons.append("EMA'ya pullback")
        if 0 < ema_dist < 2.0 and ema_cross == "bearish":
            sell_score += 0.20 * ema_w
            reasons.append("EMA'ya pullback")

        if price_change_5 > 0.3 and vol_ratio > 1.2:
            buy_score += 0.15 * momentum_w
            reasons.append(f"Hizli yukselis %{price_change_5}")
            used_indicators.append("momentum")
        if price_change_5 < -0.3 and vol_ratio > 1.2:
            sell_score += 0.15 * momentum_w
            reasons.append(f"Hizli dusus %{price_change_5}")
            used_indicators.append("momentum")

        rsi_change = teknik_analiz.get("rsi", 50) - teknik_analiz.get("rsi_prev", 50)
        if rsi_change > 3:
            buy_score += 0.10 * rsi_w
            reasons.append(f"RSI gucleniyor (+{rsi_change:.1f})")
            used_indicators.append("rsi")
        elif rsi_change < -3:
            sell_score += 0.10 * rsi_w
            reasons.append(f"RSI zayifliyor ({rsi_change:.1f})")
            used_indicators.append("rsi")

        if ob_ratio > 1.5:
            buy_score += 0.20 * ob_w
            reasons.append(f"Orderbook guclu alis ({ob_ratio})")
            used_indicators.append("orderbook")
        elif ob_sinyal == "alis_baskisi":
            buy_score += 0.10 * ob_w
            reasons.append(f"Orderbook alis ({ob_ratio})")
            used_indicators.append("orderbook")
        elif ob_ratio < 0.6:
            sell_score += 0.20 * ob_w
            reasons.append(f"Orderbook guclu satis ({ob_ratio})")
            used_indicators.append("orderbook")
        elif ob_sinyal == "satis_baskisi":
            sell_score += 0.10 * ob_w
            reasons.append(f"Orderbook satis ({ob_ratio})")
            used_indicators.append("orderbook")

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

        ai_influence = (ai_prob - 0.5) * 2 * ai_conf * 0.5
        if ai_influence > 0:
            buy_score += ai_influence
            if ai_conf > 0.3:
                reasons.append(f"AI yukselis (%{ai_prob:.0%})")
        elif ai_influence < 0:
            sell_score += abs(ai_influence)
            if ai_conf > 0.3:
                reasons.append(f"AI dusus (%{(1-ai_prob):.0%})")

        if not acik_pozisyon:
            if buy_score >= min_confidence and buy_score > sell_score:
                direction = "BUY"
                confidence = min(buy_score, 1.0)

                sl_price = round(fiyat - 1.5 * atr, 2)
                tp_price = round(fiyat + 3 * atr, 2)

                size_pct = min(max(confidence * 95, 5), 95)

                self.state["son_sinyal"] = {
                    "action": "BUY",
                    "price": fiyat,
                    "time": datetime.now().isoformat(),
                    "indicators": used_indicators,
                    "buy_score": round(buy_score, 3),
                    "sell_score": round(sell_score, 3),
                    "rsi": rsi,
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
            mevcut_kar = (fiyat - giris_fiyati) / giris_fiyati * 100 if giris_fiyati > 0 else 0

            if sell_score > buy_score and sell_score >= min_confidence:
                direction = "SELL"
                confidence = min(sell_score, 1.0)

                mevcut_kar = (fiyat - giris_fiyati) / giris_fiyati * 100 if giris_fiyati > 0 else 0

                self.state["son_sinyal"] = {
                    "action": "SELL",
                    "price": fiyat,
                    "time": datetime.now().isoformat(),
                    "indicators": used_indicators,
                    "buy_score": round(buy_score, 3),
                    "sell_score": round(sell_score, 3),
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

        son_sinyal = self.state.get("son_sinyal", {})
        indicators = son_sinyal.get("indicators", [])
        action = son_sinyal.get("action", "")

        if indicators:
            hits = self.state["weight_hits"]
            misses = self.state["weight_misses"]
            for ind in indicators:
                if kar_zarar > 0:
                    hits[ind] = hits.get(ind, 0) + 1
                else:
                    misses[ind] = misses.get(ind, 0) + 1

            w = self.state["weights"]
            for ind in indicators:
                total = hits.get(ind, 0) + misses.get(ind, 0)
                if total >= 3:
                    accuracy = hits.get(ind, 0) / total
                    if accuracy > 0.6:
                        w[ind] = min(1.5, w[ind] * 1.1)
                    elif accuracy < 0.3:
                        w[ind] = max(0.5, w[ind] * 0.9)
            self.state["weights"] = w

        self._save_state()

    def get_state(self):
        return self.state


quant_agent = QuantAgent()