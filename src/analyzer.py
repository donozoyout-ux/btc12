import pandas as pd
import numpy as np
import ta


class Analyzer:
    def analyze(self, df):
        if len(df) < 50:
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]
        price = close.iloc[-1]

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        rsi_prev = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-2]

        ema9 = ta.trend.EMAIndicator(close, window=9).ema_indicator().iloc[-1]
        ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        ema_cross = "bullish" if ema9 > ema21 else "bearish"

        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = macd.macd().iloc[-1]
        signal_line = macd.macd_signal().iloc[-1]
        macd_hist = macd.macd_diff().iloc[-1]
        macd_hist_prev = macd.macd_diff().iloc[-2]

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_pct = bb.bollinger_pband().iloc[-1]

        atr = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range().iloc[-1]

        vol_sma20 = volume.rolling(20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_sma20 if vol_sma20 > 0 else 1

        price_change_5 = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100 if close.iloc[-5] > 0 else 0

        support = close.rolling(20).min().iloc[-1]
        resistance = close.rolling(20).max().iloc[-1]

        return {
            "price": round(price, 2),
            "rsi": round(rsi, 1),
            "rsi_prev": round(rsi_prev, 1),
            "ema9": round(ema9, 2),
            "ema21": round(ema21, 2),
            "ema_cross": ema_cross,
            "macd_line": round(macd_line, 2),
            "signal_line": round(signal_line, 2),
            "macd_hist": round(macd_hist, 2),
            "macd_hist_prev": round(macd_hist_prev, 2),
            "bb_pct": round(bb_pct, 3),
            "bb_upper": round(bb_upper, 2),
            "bb_lower": round(bb_lower, 2),
            "atr": round(atr, 2),
            "atr_pct": round(atr / price * 100, 2) if price > 0 else 0,
            "vol_ratio": round(vol_ratio, 2),
            "price_change_5": round(price_change_5, 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
        }


analyzer = Analyzer()
