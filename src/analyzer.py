import json
import os
import time
from datetime import datetime
import pandas as pd
import ta
from src.config import settings


class Memory:
    def __init__(self):
        self.file = settings.memory_file
        self.trades = self._load()

    def _load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, "r") as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save(self):
        with open(self.file, "w") as f:
            json.dump(self.trades, f, indent=2, default=str)

    def record_signal(self, symbol, action, confidence, price, indicators, reason):
        entry = {
            "id": len(self.trades) + 1,
            "time": datetime.now().isoformat(),
            "symbol": symbol,
            "action": action,
            "confidence": round(confidence, 3),
            "price": price,
            "indicators": indicators,
            "reason": reason,
            "outcome": None,
            "pnl": 0,
            "closed_at": None
        }
        self.trades.append(entry)
        self._save()
        return entry["id"]

    def close_trade(self, trade_id, pnl, closed_at=None):
        for t in self.trades:
            if t["id"] == trade_id:
                t["outcome"] = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"
                t["pnl"] = round(pnl, 4)
                t["closed_at"] = closed_at or datetime.now().isoformat()
                self._save()
                return True
        return False

    def get_win_rate(self, lookback=50):
        recent = [t for t in self.trades[-lookback:] if t["outcome"]]
        if not recent:
            return {"win_rate": 0, "total": 0, "wins": 0, "losses": 0, "avg_pnl": 0}
        wins = sum(1 for t in recent if t["outcome"] == "WIN")
        losses = sum(1 for t in recent if t["outcome"] == "LOSS")
        total_pnl = sum(t["pnl"] for t in recent)
        return {
            "win_rate": round(wins / len(recent) * 100, 1),
            "total": len(recent),
            "wins": wins,
            "losses": losses,
            "avg_pnl": round(total_pnl / len(recent), 4),
            "total_pnl": round(total_pnl, 4)
        }

    def get_symbol_stats(self, symbol):
        symbol_trades = [t for t in self.trades if t["symbol"] == symbol and t["outcome"]]
        if not symbol_trades:
            return {"trades": 0, "win_rate": 0}
        wins = sum(1 for t in symbol_trades if t["outcome"] == "WIN")
        return {
            "trades": len(symbol_trades),
            "win_rate": round(wins / len(symbol_trades) * 100, 1),
            "total_pnl": round(sum(t["pnl"] for t in symbol_trades), 4)
        }

    def get_recent(self, n=10):
        return self.trades[-n:]

    def should_avoid(self, symbol):
        recent = [t for t in self.trades[-10:] if t["symbol"] == symbol and t["outcome"]]
        if len(recent) < 3:
            return False, "Yetersiz veri"
        losses = sum(1 for t in recent if t["outcome"] == "LOSS")
        if losses >= 3:
            return True, f"Son 3 islemde {losses} kez zarar"
        return False, ""


class Analyzer:
    def analyze(self, df):
        if len(df) < 30:
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]

        stoch = ta.momentum.StochRSIIndicator(close, window=14)
        sk = stoch.stochrsi_k().iloc[-1] * 100
        sd = stoch.stochrsi_d().iloc[-1] * 100

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_pct = bb.bollinger_pband().iloc[-1]
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_mid = bb.bollinger_mavg().iloc[-1]

        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        hist = macd.macd_diff().iloc[-1]
        hist_prev = macd.macd_diff().iloc[-2]

        ema9 = ta.trend.EMAIndicator(close, window=9).ema_indicator().iloc[-1]
        ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1] if len(close) > 50 else ema21

        vol_sma = volume.rolling(20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_sma if vol_sma > 0 else 1

        price = close.iloc[-1]
        price_change = close.pct_change().iloc[-1] if len(close) > 1 else 0

        atr = ta.volatility.AverageTrueRange(high, low, close, window=14)
        atr_val = atr.average_true_range().iloc[-1]
        atr_pct = (atr_val / price * 100) if price > 0 else 0

        return {
            "rsi": rsi, "sk": sk, "sd": sd,
            "bb_pct": bb_pct, "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_mid": bb_mid,
            "hist": hist, "hist_prev": hist_prev,
            "ema9": ema9, "ema21": ema21, "ema50": ema50,
            "vol_ratio": vol_ratio, "price": price,
            "price_change": price_change, "atr_pct": atr_pct
        }

    def score(self, ind, memory=None, symbol=None):
        if not ind:
            return None, 0, ""

        buy_score = 0.0
        sell_score = 0.0
        reasons = []

        rsi = ind["rsi"]
        if rsi < 25:
            buy_score += 0.25
            reasons.append(f"RSI cok dusuk ({rsi:.0f})")
        elif rsi < 30:
            buy_score += 0.15
            reasons.append(f"RSI dusuk ({rsi:.0f})")
        elif rsi < 40:
            buy_score += 0.05
        elif rsi > 75:
            sell_score += 0.25
            reasons.append(f"RSI cok yuksek ({rsi:.0f})")
        elif rsi > 70:
            sell_score += 0.15
            reasons.append(f"RSI yuksek ({rsi:.0f})")
        elif rsi > 60:
            sell_score += 0.05

        bb = ind["bb_pct"]
        if bb < 0:
            buy_score += 0.15
            reasons.append("BB altinda")
        elif bb < 0.1:
            buy_score += 0.08
        if bb > 1:
            sell_score += 0.15
            reasons.append("BB ustunde")
        elif bb > 0.9:
            sell_score += 0.08

        hist = ind["hist"]
        hist_prev = ind["hist_prev"]
        if hist > 0 and hist_prev <= 0:
            buy_score += 0.2
            reasons.append("MACD kesisim")
        elif hist > 0 and hist > hist_prev:
            buy_score += 0.08
        elif hist < 0 and hist_prev >= 0:
            sell_score += 0.2
            reasons.append("MACD kesisim negatif")
        elif hist < 0 and hist < hist_prev:
            sell_score += 0.08

        ema9 = ind["ema9"]
        ema21 = ind["ema21"]
        if ema9 > ema21:
            buy_score += 0.08
        else:
            sell_score += 0.08

        if ind["sk"] < 20 and ind["sd"] < 20:
            buy_score += 0.1
            reasons.append("Stoch asiri satim")
        elif ind["sk"] > 80 and ind["sd"] > 80:
            sell_score += 0.1
            reasons.append("Stoch asiri alim")

        vol = ind["vol_ratio"]
        if vol > 3:
            buy_score += 0.1
            sell_score += 0.1
            reasons.append(f"Hacim patlamasi ({vol:.1f}x)")
        elif vol > 2:
            buy_score += 0.05
            sell_score += 0.05

        if ind["price_change"] > 0.03:
            buy_score += 0.08
            reasons.append(f"Guc yuksek (+{ind['price_change']*100:.1f}%)")
        elif ind["price_change"] < -0.03:
            sell_score += 0.08
            reasons.append(f"Kayip yuksek ({ind['price_change']*100:.1f}%)")

        buy_score = min(buy_score, 1.0)
        sell_score = min(sell_score, 1.0)

        if memory and symbol:
            avoid, avoid_reason = memory.should_avoid(symbol)
            if avoid:
                buy_score *= 0.3
                reasons.append(f"AI UYARISI: {avoid_reason}")

            stats = memory.get_symbol_stats(symbol)
            if stats["trades"] >= 3 and stats["win_rate"] < 40:
                buy_score *= 0.5
                sell_score *= 1.2
                reasons.append(f"AI: {symbol} basari orani dusuk (%{stats['win_rate']})")

        if buy_score > 0.45 and buy_score > sell_score:
            return "BUY", buy_score, "; ".join(reasons)
        elif sell_score > 0.45 and sell_score > buy_score:
            return "SELL", sell_score, "; ".join(reasons)

        return "HOLD", max(buy_score, sell_score), f"Buy:{buy_score:.0%} Sell:{sell_score:.0%}"


analyzer = Analyzer()
