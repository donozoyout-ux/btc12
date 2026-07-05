import numpy as np
from datetime import datetime


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
        ema21 = teknik.get("ema21", 0)

        long_signal = self._check_long(sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line, price)
        short_signal = self._check_short(sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line, price)
        tp_signal = self._check_tp(wt_tci, wt_tci2, macd_hist)

        if tp_signal and short_signal is None and long_signal is None:
            return {
                "action": "SELL",
                "reason": tp_signal,
                "strict_signal": True,
                "stop_loss": 0,
                "target_profit": "VT Cross TP sinyali",
            }

        if long_signal:
            sl_price = round(price - 1.5 * atr, 2) if atr > 0 else round(price * 0.98, 2)
            tp_price = round(price + 3 * atr, 2) if atr > 0 else round(price * 1.02, 2)
            return {
                "action": "BUY",
                "reason": long_signal,
                "strict_signal": True,
                "stop_loss": sl_price,
                "target_profit": tp_price,
            }

        if short_signal:
            sl_price = round(price + 1.5 * atr, 2) if atr > 0 else round(price * 1.02, 2)
            tp_price = round(price - 3 * atr, 2) if atr > 0 else round(price * 0.98, 2)
            return {
                "action": "SELL",
                "reason": short_signal,
                "strict_signal": True,
                "stop_loss": sl_price,
                "target_profit": tp_price,
            }

        return {
            "action": "HOLD",
            "reason": self._beklenen_adim(sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line),
            "strict_signal": False,
            "stop_loss": 0,
            "target_profit": 0,
        }

    def _check_long(self, sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line, price):
        if sling_color != "GREEN":
            return None

        lookback = min(len(sling_colors), 30)
        once_red = any(c == "RED" for c in sling_colors[-lookback:-5]) if lookback > 5 else False
        if not once_red:
            return None

        recent_colors = sling_colors[-15:] if len(sling_colors) >= 15 else sling_colors
        color_swing = []
        for i in range(1, len(recent_colors)):
            if recent_colors[i] != recent_colors[i-1]:
                color_swing.append((i, recent_colors[i]))
        red_to_green = any(c[1] == "GREEN" for c in color_swing)
        if not red_to_green:
            return None

        if not (stoch_rsi_prev > 0 and stoch_rsi <= 0.5 and stoch_rsi < 5):
            return None

        macd_improving = macd_hist > macd_hist_prev
        macd_below_zero = macd_line < 0 and signal_line < 0
        macd_cross_up = macd_hist_prev <= 0 and macd_hist > 0

        if not (macd_cross_up and macd_below_zero and macd_improving):
            return None

        return f"Sling Shot YESIL + StochRSI 0 ({stoch_rsi}) + MACD sifir altinda yukari cross"

    def _check_short(self, sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line, price):
        if sling_color != "RED":
            return None

        lookback = min(len(sling_colors), 30)
        once_green = any(c == "GREEN" for c in sling_colors[-lookback:-5]) if lookback > 5 else False
        if not once_green:
            return None

        recent_colors = sling_colors[-15:] if len(sling_colors) >= 15 else sling_colors
        color_swing = []
        for i in range(1, len(recent_colors)):
            if recent_colors[i] != recent_colors[i-1]:
                color_swing.append((i, recent_colors[i]))
        green_to_red = any(c[1] == "RED" for c in color_swing)
        if not green_to_red:
            return None

        if not (stoch_rsi_prev < 100 and stoch_rsi >= 99.5 and stoch_rsi > 95):
            return None

        macd_worsening = macd_hist < macd_hist_prev
        macd_above_zero = macd_line > 0 and signal_line > 0
        macd_cross_down = macd_hist_prev >= 0 and macd_hist < 0

        if not (macd_cross_down and macd_above_zero and macd_worsening):
            return None

        return f"Sling Shot KIRMIZI + StochRSI 100 ({stoch_rsi}) + MACD sifir ustunde asagi cross"

    def _check_tp(self, wt_tci, wt_tci2, macd_hist):
        if wt_tci == 0 and wt_tci2 == 0:
            return None
        wt_diff = abs(wt_tci - wt_tci2)
        if wt_diff < 5 and (wt_tci > 60 or wt_tci < -60):
            return f"VT Cross TP: TCI={wt_tci} TCI2={wt_tci2} fark={wt_diff}"
        if abs(wt_tci) > 80:
            return f"VT Cross asiri bolge: TCI={wt_tci}"
        return None

    def _beklenen_adim(self, sling_colors, sling_color, stoch_rsi, stoch_rsi_prev, macd_hist, macd_hist_prev, macd_line, signal_line):
        if sling_color == "GREEN":
            once_red = any(c == "RED" for c in sling_colors[-20:]) if len(sling_colors) >= 20 else False
            if not once_red:
                return "Once KIRMIZI trend bekleniyor"
            if stoch_rsi > 5:
                return f"StochRSI 0 bekleniyor (su an: {stoch_rsi})"
            macd_below_zero = macd_line < 0 and signal_line < 0
            macd_cross_up = macd_hist_prev <= 0 and macd_hist > 0
            if not macd_below_zero:
                return "MACD sifir altina inmesi bekleniyor"
            if not macd_cross_up:
                return "MACD sifir altinda yukari cross bekleniyor"
            return "LONG kosullari kontrol ediliyor"
        elif sling_color == "RED":
            once_green = any(c == "GREEN" for c in sling_colors[-20:]) if len(sling_colors) >= 20 else False
            if not once_green:
                return "Once YESIL trend bekleniyor"
            if stoch_rsi < 95:
                return f"StochRSI 100 bekleniyor (su an: {stoch_rsi})"
            macd_above_zero = macd_line > 0 and signal_line > 0
            macd_cross_down = macd_hist_prev >= 0 and macd_hist < 0
            if not macd_above_zero:
                return "MACD sifir ustune cikmasi bekleniyor"
            if not macd_cross_down:
                return "MACD sifir ustunde asagi cross bekleniyor"
            return "SHORT kosullari kontrol ediliyor"
        return "Sling Shot rengi belirlenemiyor"


signal_strategy = SignalStrategy()