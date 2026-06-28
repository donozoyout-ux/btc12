import pandas as pd
import ta
import numpy as np


class VolumeAgent:
    name = "VOLUME"
    icon = "bar_chart"

    def analyze(self, df):
        if len(df) < 30:
            return {"direction": "NEUTRAL", "confidence": 0, "reason": "Yetersiz veri"}

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        vol_sma20 = volume.rolling(20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_sma20 if vol_sma20 > 0 else 1

        obv = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        obv_sma = obv.rolling(20).mean().iloc[-1]
        obv_prev = obv.iloc[-2]
        obv_now = obv.iloc[-1]

        mfi = ta.volume.MFIMoneyFlowIndex(high, low, close, volume, window=14).money_flow_index().iloc[-1]

        vwma = (close * volume).rolling(20).sum() / volume.rolling(20).sum()
        vwap = vwma.iloc[-1]
        price = close.iloc[-1]

        typical_price = (high + low + close) / 3
        tp_vol = typical_price * volume
        vwap_cum = tp_vol.sum() / volume.sum()

        buy = 0
        sell = 0
        reasons = []

        if vol_ratio > 3:
            buy += 0.15
            sell += 0.15
            reasons.append(f"Hacim patlamasi ({vol_ratio:.1f}x)")
        elif vol_ratio > 2:
            buy += 0.1
            sell += 0.1
            reasons.append(f"Yuksek hacim ({vol_ratio:.1f}x)")
        elif vol_ratio < 0.5:
            reasons.append(f"Dusuk hacim ({vol_ratio:.1f}x)")

        if obv_now > obv_prev and obv_now > obv_sma:
            buy += 0.2
            reasons.append("OBV yukari trend")
        elif obv_now < obv_prev and obv_now < obv_sma:
            sell += 0.2
            reasons.append("OBV asagi trend")

        if obv_now > obv_prev and close.iloc[-1] < close.iloc[-2]:
            buy += 0.15
            reasons.append("OBV fyat uyusmazligi (alis)")
        elif obv_now < obv_prev and close.iloc[-1] > close.iloc[-2]:
            sell += 0.15
            reasons.append("OBV fyat uyusmazligi (satis)")

        if mfi < 20:
            buy += 0.25
            reasons.append(f"MFI asiri satim ({mfi:.0f})")
        elif mfi < 30:
            buy += 0.1
        elif mfi > 80:
            sell += 0.25
            reasons.append(f"MFI asiri alim ({mfi:.0f})")
        elif mfi > 70:
            sell += 0.1

        if price > vwap:
            buy += 0.1
            reasons.append("Fiyat VWAP ustunde")
        else:
            sell += 0.1
            reasons.append("Fiyat VWAP altinda")

        vol_increasing = volume.iloc[-1] > volume.iloc[-2] > volume.iloc[-3]
        vol_decreasing = volume.iloc[-1] < volume.iloc[-2] < volume.iloc[-3]
        if vol_increasing:
            reasons.append("Hacim artiyor")
        elif vol_decreasing:
            reasons.append("Hacim azaliyor")

        buy = min(buy, 1.0)
        sell = min(sell, 1.0)

        if buy > sell and buy > 0.25:
            return {"direction": "BUY", "confidence": buy, "reason": "; ".join(reasons)}
        elif sell > buy and sell > 0.25:
            return {"direction": "SELL", "confidence": sell, "reason": "; ".join(reasons)}
        return {"direction": "NEUTRAL", "confidence": max(buy, sell), "reason": "Hacim nötr"}
