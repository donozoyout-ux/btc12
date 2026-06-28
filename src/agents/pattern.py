import pandas as pd
import numpy as np


class PatternAgent:
    name = "PATTERN"
    icon = "candlestick"

    def analyze(self, df):
        if len(df) < 30:
            return {"direction": "NEUTRAL", "confidence": 0, "reason": "Yetersiz veri"}

        o = df["open"].values
        h = df["high"].values
        l = df["low"].values
        c = df["close"].values
        price = c[-1]

        buy = 0
        sell = 0
        reasons = []

        body = c[-1] - o[-1]
        upper_shadow = h[-1] - max(o[-1], c[-1])
        lower_shadow = min(o[-1], c[-1]) - l[-1]
        total_range = h[-1] - l[-1]

        if total_range > 0:
            body_ratio = abs(body) / total_range
            lower_ratio = lower_shadow / total_range
            upper_ratio = upper_shadow / total_range
        else:
            body_ratio = lower_ratio = upper_ratio = 0

        if body < 0 and lower_shadow > abs(body) * 2 and body_ratio < 0.3:
            buy += 0.25
            reasons.append("Çekiç formasyonu")
        elif body > 0 and upper_shadow > body * 2 and body_ratio < 0.3:
            sell += 0.25
            reasons.append("Karama formasyonu")

        if abs(body) < total_range * 0.1 and total_range > 0:
            reasons.append("Doji formasyonu (belirsizlik)")

        if body > 0 and c[-1] > c[-2] and c[-2] > c[-3] and o[-1] < c[-2]:
            buy += 0.15
            reasons.append("3 yukari momentum")

        if body < 0 and c[-1] < c[-2] and c[-2] < c[-3] and o[-1] > c[-2]:
            sell += 0.15
            reasons.append("3 asagi momentum")

        if body > 0 and body > (c[-2] - o[-2]) * 1.5 and c[-1] > c[-2]:
            buy += 0.1
            reasons.append("Guclu yukari mum")

        if body < 0 and abs(body) > abs(c[-2] - o[-2]) * 1.5 and c[-1] < c[-2]:
            sell += 0.1
            reasons.append("Guclu asagi mum")

        highs = df["high"].values
        lows = df["low"].values

        recent_highs = highs[-20:]
        recent_lows = lows[-20:]

        resistance = np.max(recent_highs)
        support = np.min(recent_lows)
        range_size = resistance - support

        if range_size > 0:
            pos_in_range = (price - support) / range_size

            if pos_in_range < 0.2:
                buy += 0.15
                reasons.append(f"Destek yakini (${support:,.0f})")
            elif pos_in_range > 0.8:
                sell += 0.15
                reasons.append(f"Direnç yakini (${resistance:,.0f})")

        fib_382 = resistance - range_size * 0.382
        fib_618 = resistance - range_size * 0.618

        if abs(price - fib_382) / price < 0.005:
            reasons.append("Fib 38.2 yakini")
            buy += 0.05
        elif abs(price - fib_618) / price < 0.005:
            reasons.append("Fib 61.8 yakini")
            buy += 0.05

        swing_highs = []
        swing_lows = []
        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                swing_highs.append(highs[i])
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                swing_lows.append(lows[i])

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            if price > max(swing_highs[-2:]):
                buy += 0.1
                reasons.append("Yukari breakout")
            elif price < min(swing_lows[-2:]):
                sell += 0.1
                reasons.append("Asagi breakout")

        buy = min(buy, 1.0)
        sell = min(sell, 1.0)

        if buy > sell and buy > 0.2:
            return {"direction": "BUY", "confidence": buy, "reason": "; ".join(reasons)}
        elif sell > buy and sell > 0.2:
            return {"direction": "SELL", "confidence": sell, "reason": "; ".join(reasons)}
        return {"direction": "NEUTRAL", "confidence": max(buy, sell), "reason": "Pattern nötr"}
