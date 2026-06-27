import pandas as pd
import numpy as np
import ta
from dataclasses import dataclass
from typing import Optional
from src.config import settings


@dataclass
class Signal:
    action: str
    reason: str
    confidence: float
    price: float
    rsi: float
    bb_upper: float
    bb_lower: float
    bb_middle: float
    volume_ratio: float
    price_change_pct: float


class Strategy:
    def __init__(self):
        self.rsi_period = settings.rsi_period
        self.rsi_overbought = settings.rsi_overbought
        self.rsi_oversold = settings.rsi_oversold
        self.bb_period = settings.bb_period
        self.bb_std = settings.bb_std
        self.volume_spike_multiplier = settings.volume_spike_multiplier
        self.price_change_threshold = settings.price_change_threshold

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # RSI
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=self.rsi_period).rsi()

        # Stochastic RSI
        stoch = ta.momentum.StochRSIIndicator(df["close"], window=14)
        df["stoch_k"] = stoch.stochrsi_k() * 100
        df["stoch_d"] = stoch.stochrsi_d() * 100

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df["close"], window=self.bb_period, window_dev=self.bb_std)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        df["bb_pct"] = bb.bollinger_pband()

        # MACD
        macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"] = macd.macd_diff()

        # EMA Cross
        df["ema9"] = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator()
        df["ema21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()
        df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

        # Volume
        df["volume_sma"] = df["volume"].rolling(window=20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"].replace(0, 1)

        # Price change
        df["price_change_pct"] = df["close"].pct_change()
        df["price_change_5"] = df["close"].pct_change(5)

        # ATR for volatility
        atr = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14)
        df["atr"] = atr.average_true_range()
        df["atr_pct"] = df["atr"] / df["close"] * 100

        return df

    def analyze(self, df: pd.DataFrame) -> Optional[Signal]:
        if len(df) < 55:
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        current_price = latest["close"]
        rsi = latest["rsi"]
        bb_upper = latest["bb_upper"]
        bb_lower = latest["bb_lower"]
        bb_middle = latest["bb_middle"]
        bb_pct = latest["bb_pct"]
        volume_ratio = latest["volume_ratio"]
        price_change = latest["price_change_pct"]
        macd_hist = latest["macd_hist"]
        macd_hist_prev = prev["macd_hist"]
        stoch_k = latest["stoch_k"]
        stoch_d = latest["stoch_d"]
        ema9 = latest["ema9"]
        ema21 = latest["ema21"]
        ema50 = latest["ema50"]

        if pd.isna(rsi) or pd.isna(bb_upper) or pd.isna(volume_ratio) or pd.isna(macd_hist):
            return None

        buy_score = 0.0
        sell_score = 0.0
        reasons = []

        # --- RSI ---
        if rsi < 25:
            buy_score += 0.25
            reasons.append(f"RSI cok dusuk ({rsi:.0f})")
        elif rsi < 30:
            buy_score += 0.15
            reasons.append(f"RSI dusuk ({rsi:.0f})")
        elif rsi < 40:
            buy_score += 0.05

        if rsi > 75:
            sell_score += 0.25
            reasons.append(f"RSI cok yuksek ({rsi:.0f})")
        elif rsi > 70:
            sell_score += 0.15
            reasons.append(f"RSI yuksek ({rsi:.0f})")
        elif rsi > 60:
            sell_score += 0.05

        # --- Bollinger Bands ---
        if bb_pct < 0:
            buy_score += 0.15
            reasons.append("Fiyat BB altinda")
        elif bb_pct < 0.1:
            buy_score += 0.08

        if bb_pct > 1:
            sell_score += 0.15
            reasons.append("Fiyat BB ustunde")
        elif bb_pct > 0.9:
            sell_score += 0.08

        if latest["bb_width"] < 0.03:
            buy_score += 0.1
            sell_score += 0.1
            reasons.append("BB Sikisma (volatilite dusuk)")

        # --- MACD ---
        if macd_hist > 0 and macd_hist_prev <= 0:
            buy_score += 0.2
            reasons.append("MACD pozitife dondu")
        elif macd_hist > 0 and macd_hist > macd_hist_prev:
            buy_score += 0.1
            reasons.append("MACD gucleniyor")

        if macd_hist < 0 and macd_hist_prev >= 0:
            sell_score += 0.2
            reasons.append("MACD negatife dondu")
        elif macd_hist < 0 and macd_hist < macd_hist_prev:
            sell_score += 0.1
            reasons.append("MACD zayifliyor")

        # --- EMA Cross ---
        if ema9 > ema21 and prev["ema9"] <= prev["ema21"]:
            buy_score += 0.15
            reasons.append("EMA 9/21 kesisim (alis)")
        elif ema9 > ema21:
            buy_score += 0.05

        if ema9 < ema21 and prev["ema9"] >= prev["ema21"]:
            sell_score += 0.15
            reasons.append("EMA 9/21 kesisim (satis)")
        elif ema9 < ema21:
            sell_score += 0.05

        if current_price > ema50:
            buy_score += 0.05
        else:
            sell_score += 0.05

        # --- Stochastic ---
        if stoch_k < 20 and stoch_d < 20:
            buy_score += 0.1
            reasons.append("Stochastic asiri satim bolgesinde")
        elif stoch_k > 80 and stoch_d > 80:
            sell_score += 0.1
            reasons.append("Stochastic asiri alim bolgesinde")

        if stoch_k > stoch_d and prev["stoch_k"] <= prev["stoch_d"]:
            buy_score += 0.08
            reasons.append("Stochastic yukari kesisim")
        elif stoch_k < stoch_d and prev["stoch_k"] >= prev["stoch_d"]:
            sell_score += 0.08
            reasons.append("Stochastic asagi kesisim")

        # --- Volume ---
        if volume_ratio > 3:
            multiplier = 0.15
            reasons.append(f"Hacim patlamasi ({volume_ratio:.1f}x)")
        elif volume_ratio > 2:
            multiplier = 0.1
            reasons.append(f"Yuksek hacim ({volume_ratio:.1f}x)")
        elif volume_ratio > 1.5:
            multiplier = 0.05
        else:
            multiplier = 0

        buy_score += multiplier
        sell_score += multiplier

        # --- Fiyat Degisimi ---
        if price_change > 0.05:
            buy_score += 0.1
            reasons.append(f"Guc yuksek (+{price_change*100:.1f}%)")
        elif price_change < -0.05:
            sell_score += 0.1
            reasons.append(f"Kayip yuksek ({price_change*100:.1f}%)")

        # --- SONUC ---
        buy_score = min(buy_score, 1.0)
        sell_score = min(sell_score, 1.0)

        if buy_score > 0.4 and buy_score > sell_score:
            return Signal(
                action="BUY",
                reason="; ".join(reasons) if reasons else "Alis sinyali",
                confidence=buy_score,
                price=current_price,
                rsi=rsi,
                bb_upper=bb_upper,
                bb_lower=bb_lower,
                bb_middle=bb_middle,
                volume_ratio=volume_ratio,
                price_change_pct=price_change
            )
        elif sell_score > 0.4 and sell_score > buy_score:
            return Signal(
                action="SELL",
                reason="; ".join(reasons) if reasons else "Satis sinyali",
                confidence=sell_score,
                price=current_price,
                rsi=rsi,
                bb_upper=bb_upper,
                bb_lower=bb_lower,
                bb_middle=bb_middle,
                volume_ratio=volume_ratio,
                price_change_pct=price_change
            )
        else:
            return Signal(
                action="HOLD",
                reason=f"Buy:{buy_score:.0%} Sell:{sell_score:.0%} - net sinyal yok",
                confidence=max(buy_score, sell_score),
                price=current_price,
                rsi=rsi,
                bb_upper=bb_upper,
                bb_lower=bb_lower,
                bb_middle=bb_middle,
                volume_ratio=volume_ratio,
                price_change_pct=price_change
            )