import numpy as np
from src.ai_engine import ai_engine


class MLAgent:
    name = "AI_ML"
    icon = "brain"

    def analyze(self, df, symbol=None):
        if len(df) < 30:
            return {"direction": "NEUTRAL", "confidence": 0, "reason": "Yetersiz veri"}

        try:
            indicators = self._extract_indicators(df)
            prediction = ai_engine.predict(indicators)

            if prediction is None:
                return {"direction": "NEUTRAL", "confidence": 0, "reason": "Model henuz hazir degil"}

            ml_pred = prediction.get("prediction", "HOLD")
            win_prob = prediction.get("win_probability", 0.5)
            confidence = prediction.get("confidence", 0)
            factors = prediction.get("top_factors", [])

            if ml_pred == "BUY" and win_prob > 0.55:
                direction = "BUY"
                conf = min(confidence * 1.2, 1.0)
            elif ml_pred == "SELL" and win_prob < 0.45:
                direction = "SELL"
                conf = min(confidence * 1.2, 1.0)
            else:
                direction = "NEUTRAL"
                conf = confidence

            reason_parts = []
            if factors:
                reason_parts.append(f"Guclu faktorler: {', '.join(factors[:3])}")
            reason_parts.append(f"Kazanma olasiligi: %{win_prob*100:.1f}")

            return {
                "direction": direction,
                "confidence": conf,
                "reason": "ML: " + "; ".join(reason_parts)
            }

        except Exception as e:
            return {"direction": "NEUTRAL", "confidence": 0, "reason": f"ML hata: {str(e)[:50]}"}

    def _extract_indicators(self, df):
        import ta

        close = df["close"]
        high = df["high"]
        low = df["low"]

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        stoch = ta.momentum.StochRSIIndicator(close, window=14)
        sk = stoch.stochrsi_k().iloc[-1] * 100
        sd = stoch.stochrsi_d().iloc[-1] * 100

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_pct = bb.bollinger_pband().iloc[-1]

        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        hist = macd.macd_diff().iloc[-1]
        hist_prev = macd.macd_diff().iloc[-2] if len(close) > 1 else 0

        ema9 = ta.trend.EMAIndicator(close, window=9).ema_indicator().iloc[-1]
        ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]

        vol_ratio = 1
        vol_mean = df["volume"].rolling(20).mean().iloc[-1]
        if vol_mean > 0:
            vol_ratio = df["volume"].iloc[-1] / vol_mean

        price_change = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] if close.iloc[-5] > 0 else 0

        tr = __import__('pandas').concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr_pct = tr.rolling(14).mean().iloc[-1] / close.iloc[-1] if close.iloc[-1] > 0 else 0

        return {
            "rsi": rsi if not np.isnan(rsi) else 50,
            "sk": sk if not np.isnan(sk) else 50,
            "sd": sd if not np.isnan(sd) else 50,
            "bb_pct": bb_pct if not np.isnan(bb_pct) else 0.5,
            "hist": hist if not np.isnan(hist) else 0,
            "hist_prev": hist_prev if not np.isnan(hist_prev) else 0,
            "ema9": ema9 if not np.isnan(ema9) else close.iloc[-1],
            "ema21": ema21 if not np.isnan(ema21) else close.iloc[-1],
            "vol_ratio": vol_ratio,
            "price_change": price_change,
            "atr_pct": atr_pct if not np.isnan(atr_pct) else 0,
        }


ml_agent = MLAgent()
