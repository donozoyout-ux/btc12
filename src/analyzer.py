import json
import os
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
            return False, ""
        losses = sum(1 for t in recent if t["outcome"] == "LOSS")
        if losses >= 3:
            return True, f"AI: {symbol} son {len(recent)} islemde {losses} kez zarar"
        return False, ""


class Analyzer:
    def analyze(self, df):
        if len(df) < 30:
            return None

        from src.agents.coordinator import coordinator
        result = coordinator.analyze_all(df)

        return {
            "direction": result["direction"],
            "confidence": result["confidence"],
            "buy_score": result["buy_score"],
            "sell_score": result["sell_score"],
            "consensus": result["consensus"],
            "agents": result["agents"],
            "reasons": result["reasons"],
            "summary": result["summary"],
            "price": df["close"].iloc[-1],
            "rsi": ta.momentum.RSIIndicator(df["close"], window=14).rsi().iloc[-1],
            "volume_ratio": df["volume"].iloc[-1] / df["volume"].rolling(20).mean().iloc[-1] if df["volume"].rolling(20).mean().iloc[-1] > 0 else 1
        }


analyzer = Analyzer()
