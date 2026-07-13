import numpy as np
from datetime import datetime
from src.config import settings


class SignalStrategy:
    def analyze(self, teknik):
        if not teknik or "price" not in teknik:
            return {"action": "HOLD", "reason": "Veri yok", "strict_signal": False}

        sling_colors = teknik.get("sling_colors", [])
        sling_color = teknik.get("sling_color", "RED")
        stoch_rsi = teknik.get("stoch_rsi", 50)
        stoch_rsi_prev = teknik.get("stoch_rsi_prev", 50)
        macd_hist = teknik.get("macd_hist", 0)
        macd_hist_prev = teknik.get("macd_hist_prev", 0)
        macd_line = teknik.get("macd_line", 0)
        signal_line = teknik.get("signal_line", 0)
        wt_tci = teknik.get("wt_tci", 0)
        wt_tci2 = teknik.get("wt_tci2", 0)
        price = teknik["price"]
        atr = teknik.get("atr", 0)
        rsi = teknik.get("rsi", 50)
        bb_pct = teknik.get("bb_pct", 0.5)
        vol_ratio = teknik.get("vol_ratio", 1.0)

        long_score = self._check_long_score(sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line, price, rsi, bb_pct, vol_ratio)
        short_score = self._check_short_score(sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line, price, rsi, bb_pct, vol_ratio)
        tp_signal = self._check_tp(wt_tci, wt_tci2, macd_hist)

        if tp_signal and short_score < 0 and long_score <= 0:
            return {
                "action": "SELL",
                "reason": tp_signal,
                "strict_signal": True,
                "stop_loss": 0,
                "target_profit": "VT Cross TP sinyali",
                "long_score": long_score,
                "short_score": short_score,
            }

        if long_score >= 3:
            sl_price, tp_price = self._scalp_sl_tp(price, atr)
            return {
                "action": "BUY",
                "reason": f"Puan: {long_score}/5",
                "strict_signal": True,
                "stop_loss": sl_price,
                "target_profit": tp_price,
                "long_score": long_score,
                "short_score": short_score,
            }

        if short_score >= 3:
            sl_price, tp_price = self._scalp_sl_tp(price, atr)
            return {
                "action": "SELL",
                "reason": f"Puan: {short_score}/5",
                "strict_signal": True,
                "stop_loss": sl_price,
                "target_profit": tp_price,
                "long_score": long_score,
                "short_score": short_score,
            }

        return {
            "action": "HOLD",
            "reason": self._beklenen_adim(sling_colors, sling_color, stoch_rsi, long_score, short_score),
            "strict_signal": False,
            "stop_loss": 0,
            "target_profit": 0,
            "long_score": long_score,
            "short_score": short_score,
        }

    def _check_long_score(self, sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line, price, rsi, bb_pct, vol_ratio):
        score = 0
        if sling_color == "GREEN":
            score += 1

        lookback = min(len(sling_colors), 15)
        if lookback > 3:
            once_red = any(c == "RED" for c in sling_colors[-lookback:-2])
            if once_red:
                score += 1

        if stoch_rsi < 15:
            score += 1

        macd_cross_up = macd_hist_prev <= 0 and macd_hist > 0
        if macd_cross_up:
            score += 1
        elif macd_hist > macd_hist_prev and macd_hist > -0.5:
            score += 0.5

        if rsi < 40:
            score += 0.5
        if bb_pct < 0.2:
            score += 0.5
        if vol_ratio > 1.5:
            score += 0.5

        return score

    def _check_short_score(self, sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line, price, rsi, bb_pct, vol_ratio):
        score = 0
        if sling_color == "RED":
            score += 1

        lookback = min(len(sling_colors), 15)
        if lookback > 3:
            once_green = any(c == "GREEN" for c in sling_colors[-lookback:-2])
            if once_green:
                score += 1

        if stoch_rsi > 85:
            score += 1

        macd_cross_down = macd_hist_prev >= 0 and macd_hist < 0
        if macd_cross_down:
            score += 1
        elif macd_hist < macd_hist_prev and macd_hist < 0.5:
            score += 0.5

        if rsi > 60:
            score += 0.5
        if bb_pct > 0.8:
            score += 0.5
        if vol_ratio > 1.5:
            score += 0.5

        return score

    def _check_tp(self, wt_tci, wt_tci2, macd_hist):
        if wt_tci == 0 and wt_tci2 == 0:
            return None
        wt_diff = abs(wt_tci - wt_tci2)
        if wt_diff < 5 and (wt_tci > 60 or wt_tci < -60):
            return f"VT Cross TP: TCI={wt_tci} TCI2={wt_tci2}"
        if abs(wt_tci) > 80:
            return f"VT Cross asiri bolge: TCI={wt_tci}"
        return None

    def _scalp_sl_tp(self, price, atr):
        """
        Kısa vadeli (M10/M30) scalping için DİNAMİK stop-loss / take-profit.
        ATR'a göre ölçeklenir, ayarlanabilir maksimum yüzde cap'iyle sınırlanır.
        """
        if atr and atr > 0:
            sl_atr = price - settings.scalp_sl_atr_mult * atr
            tp_atr = price + settings.scalp_tp_atr_mult * atr
        else:
            sl_atr = float("-inf")
            tp_atr = float("inf")
        sl_cap = price * (1 - settings.scalp_max_sl_pct / 100.0)
        tp_cap = price * (1 + settings.scalp_max_tp_pct / 100.0)

        sl_price = max(sl_atr, sl_cap)
        tp_price = min(tp_atr, tp_cap)

        if tp_price <= sl_price:
            tp_price = round(price * 1.004, 2)

        return round(sl_price, 2), round(tp_price, 2)

    def _beklenen_adim(self, sling_colors, sling_color, stoch_rsi, long_score, short_score):
        if sling_color == "GREEN":
            if long_score < 1:
                return "Sling Shot YESIL ama baska gosterge yok"
            if long_score < 2:
                return "StochRSI veya MACD bekleniyor"
            if long_score < 3:
                return f"Skor artirilmali ({long_score}/3)"
            return "LONG kosullari tamam"
        elif sling_color == "RED":
            if short_score < 1:
                return "Sling Shot KIRMIZI ama baska gosterge yok"
            if short_score < 2:
                return "StochRSI veya MACD bekleniyor"
            if short_score < 3:
                return f"Skor artirilmali ({short_score}/3)"
            return "SHORT kosullari tamam"
        return "Trend bekleniyor"


signal_strategy = SignalStrategy()
