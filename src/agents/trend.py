import pandas as pd
import ta
import numpy as np


class TrendAgent:
    name = "TREND"
    icon = "trending_up"

    def analyze(self, df):
        if len(df) < 60:
            return {"direction": "NEUTRAL", "confidence": 0, "reason": "Yetersiz veri"}

        close = df["close"]
        high = df["high"]
        low = df["low"]

        adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
        adx = adx_ind.adx().iloc[-1]
        plus_di = adx_ind.adx_pos().iloc[-1]
        minus_di = adx_ind.adx_neg().iloc[-1]

        ichimoku = ta.trend.IchimokuIndicator(high, low, window1=9, window2=26, window3=52)
        tenkan = ichimoku.ichimoku_conversion_line().iloc[-1]
        kijun = ichimoku.ichimoku_base_line().iloc[-1]
        span_a = ichimoku.ichimoku_a().iloc[-1]
        span_b = ichimoku.ichimoku_b().iloc[-1]

        price = close.iloc[-1]

        psar = ta.trend.PSARIndicator(high, low, close)
        psar_val = psar.psar().iloc[-1]
        psar_up = psar.psar_up().iloc[-1]
        psar_down = psar.psar_down().iloc[-1]

        ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1]
        ema200 = ta.trend.EMAIndicator(close, window=200).ema_indicator().iloc[-1] if len(close) > 200 else ema50

        buy = 0
        sell = 0
        reasons = []

        if adx > 25:
            if plus_di > minus_di:
                buy += 0.25
                reasons.append(f"Guclu yukari trend (ADX:{adx:.0f})")
            else:
                sell += 0.25
                reasons.append(f"Guclu asagi trend (ADX:{adx:.0f})")
        elif adx < 20:
            reasons.append(f"Zayif trend (ADX:{adx:.0f})")

        if price > tenkan and tenkan > kijun:
            buy += 0.2
            reasons.append("Ichimoku bullish")
        elif price < tenkan and tenkan < kijun:
            sell += 0.2
            reasons.append("Ichimoku bearish")

        cloud_top = max(span_a, span_b)
        cloud_bottom = min(span_a, span_b)
        if price > cloud_top:
            buy += 0.1
            if span_a > span_b:
                buy += 0.1
                reasons.append("Bulut yukaridan (Tenkan > Kijun)")
        elif price < cloud_bottom:
            sell += 0.1
            if span_a < span_b:
                sell += 0.1
                reasons.append("Bulut asagidan (Tenkan < Kijun)")

        if tenkan > kijun:
            buy += 0.05
        else:
            sell += 0.05

        if price > psar_val:
            buy += 0.15
            reasons.append("PSAR yukari")
        else:
            sell += 0.15
            reasons.append("PSAR asagi")

        if len(close) > 200:
            if ema50 > ema200:
                buy += 0.1
                reasons.append("Altin kesisim (50>200)")
            else:
                sell += 0.1
                reasons.append("OLUM kesisim (50<200)")

        buy = min(buy, 1.0)
        sell = min(sell, 1.0)

        if buy > sell and buy > 0.25:
            return {"direction": "BUY", "confidence": buy, "reason": "; ".join(reasons)}
        elif sell > buy and sell > 0.25:
            return {"direction": "SELL", "confidence": sell, "reason": "; ".join(reasons)}
        return {"direction": "NEUTRAL", "confidence": max(buy, sell), "reason": "Trend belirsiz"}
