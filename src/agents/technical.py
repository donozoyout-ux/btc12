import pandas as pd
import ta


class TechnicalAgent:
    name = "TECHNICAL"
    icon = "chart"

    def analyze(self, df):
        if len(df) < 50:
            return {"direction": "NEUTRAL", "confidence": 0, "reason": "Yetersiz veri"}

        close = df["close"]
        high = df["high"]
        low = df["low"]

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        rsi_prev = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-2]

        stoch = ta.momentum.StochRSIIndicator(close, window=14)
        sk = stoch.stochrsi_k().iloc[-1] * 100
        sd = stoch.stochrsi_d().iloc[-1] * 100

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_pct = bb.bollinger_pband().iloc[-1]

        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        hist = macd.macd_diff().iloc[-1]
        hist_prev = macd.macd_diff().iloc[-2]

        ema9 = ta.trend.EMAIndicator(close, window=9).ema_indicator().iloc[-1]
        ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1] if len(close) > 50 else ema21

        buy = 0
        sell = 0
        reasons = []

        if rsi < 30:
            buy += 0.3
            reasons.append(f"RSI asiri satim ({rsi:.0f})")
        elif rsi < 40:
            buy += 0.1
        elif rsi > 70:
            sell += 0.3
            reasons.append(f"RSI asiri alim ({rsi:.0f})")
        elif rsi > 60:
            sell += 0.1

        if rsi < rsi_prev and rsi < 35:
            buy += 0.1
            reasons.append("RSI toparliyor")

        if bb_pct < 0:
            buy += 0.2
            reasons.append("BB altinda")
        elif bb_pct < 0.1:
            buy += 0.1
        elif bb_pct > 1:
            sell += 0.2
            reasons.append("BB ustunde")
        elif bb_pct > 0.9:
            sell += 0.1

        if hist > 0 and hist_prev <= 0:
            buy += 0.2
            reasons.append("MACD altin kesisim")
        elif hist > 0 and hist > hist_prev:
            buy += 0.1
        elif hist < 0 and hist_prev >= 0:
            sell += 0.2
            reasons.append("MACD olum kesisim")
        elif hist < 0 and hist < hist_prev:
            sell += 0.1

        if ema9 > ema21:
            buy += 0.1
        else:
            sell += 0.1

        if ema9 > ema21 and ema21 > ema50:
            buy += 0.1
            reasons.append("EMA sirali yukari")
        elif ema9 < ema21 and ema21 < ema50:
            sell += 0.1
            reasons.append("EMA sirali asagi")

        if sk < 20 and sd < 20:
            buy += 0.15
            reasons.append("Stoch asiri satim")
        elif sk > 80 and sd > 80:
            sell += 0.15
            reasons.append("Stoch asiri alim")

        buy = min(buy, 1.0)
        sell = min(sell, 1.0)

        if buy > sell and buy > 0.3:
            return {"direction": "BUY", "confidence": buy, "reason": "; ".join(reasons)}
        elif sell > buy and sell > 0.3:
            return {"direction": "SELL", "confidence": sell, "reason": "; ".join(reasons)}
        return {"direction": "NEUTRAL", "confidence": max(buy, sell), "reason": "Net sinyal yok"}
