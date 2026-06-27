import pandas as pd
import numpy as np
import ta
from dataclasses import dataclass
from typing import Optional
from src.config import settings


@dataclass
class Signal:
    action: str  # "BUY", "SELL", "HOLD"
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

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df["close"], window=self.bb_period, window_dev=self.bb_std)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

        # Volume
        df["volume_sma"] = df["volume"].rolling(window=20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]

        # Price change
        df["price_change_pct"] = df["close"].pct_change()

        return df

    def analyze(self, df: pd.DataFrame) -> Optional[Signal]:
        if len(df) < max(self.rsi_period, self.bb_period) + 5:
            return None

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        current_price = latest["close"]
        rsi = latest["rsi"]
        bb_upper = latest["bb_upper"]
        bb_lower = latest["bb_lower"]
        bb_middle = latest["bb_middle"]
        volume_ratio = latest["volume_ratio"]
        price_change_pct = latest["price_change_pct"]

        # Skip if NaN
        if pd.isna(rsi) or pd.isna(bb_upper) or pd.isna(volume_ratio):
            return None

        # Signal detection
        signals = []
        confidence = 0.0

        # 1. RSI Oversold + Price near lower BB = Potential BUY
        if rsi < self.rsi_oversold and current_price <= bb_lower * 1.01:
            signals.append(f"RSI oversold ({rsi:.1f}) + price at lower BB")
            confidence += 0.4

        # 2. RSI Overbought + Price near upper BB = Potential SELL
        if rsi > self.rsi_overbought and current_price >= bb_upper * 0.99:
            signals.append(f"RSI overbought ({rsi:.1f}) + price at upper BB")
            confidence += 0.4

        # 3. Volume spike
        if volume_ratio > self.volume_spike_multiplier:
            signals.append(f"Volume spike ({volume_ratio:.1f}x avg)")
            confidence += 0.3

        # 4. Price breakout from BB
        if price_change_pct > self.price_change_threshold and current_price > bb_upper:
            signals.append(f"Bullish breakout: +{price_change_pct*100:.1f}% above upper BB")
            confidence += 0.3
        elif price_change_pct < -self.price_change_threshold and current_price < bb_lower:
            signals.append(f"Bearish breakdown: {price_change_pct*100:.1f}% below lower BB")
            confidence += 0.3

        # 5. BB Squeeze (low volatility) + volume spike = potential breakout
        if latest["bb_width"] < 0.05 and volume_ratio > 1.5:
            signals.append(f"BB Squeeze + volume ({latest['bb_width']:.3f} width)")
            confidence += 0.2

        if not signals:
            return Signal(
                action="HOLD",
                reason="No significant signal detected",
                confidence=0.0,
                price=current_price,
                rsi=rsi,
                bb_upper=bb_upper,
                bb_lower=bb_lower,
                bb_middle=bb_middle,
                volume_ratio=volume_ratio,
                price_change_pct=price_change_pct
            )

        # Determine action
        buy_signals = any("oversold" in s.lower() or "bullish" in s.lower() or "squeeze" in s.lower() for s in signals)
        sell_signals = any("overbought" in s.lower() or "bearish" in s.lower() for s in signals)

        if buy_signals and not sell_signals:
            action = "BUY"
        elif sell_signals and not buy_signals:
            action = "SELL"
        else:
            action = "HOLD"

        return Signal(
            action=action,
            reason="; ".join(signals),
            confidence=min(confidence, 1.0),
            price=current_price,
            rsi=rsi,
            bb_upper=bb_upper,
            bb_lower=bb_lower,
            bb_middle=bb_middle,
            volume_ratio=volume_ratio,
            price_change_pct=price_change_pct
        )