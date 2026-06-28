import json
import os
import numpy as np
from datetime import datetime
from src.config import settings


class AIEngine:
    def __init__(self):
        self.model_file = "ai_model.json"
        self.history_file = "ai_history.json"
        self.model = None
        self.history = self._load_history()
        self.min_samples = 10
        self._try_load_model()

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_history(self):
        with open(self.history_file, "w") as f:
            json.dump(self.history, f, indent=2, default=str)

    def _try_load_model(self):
        if os.path.exists(self.model_file):
            try:
                from sklearn.ensemble import RandomForestClassifier
                import joblib
                self.model = joblib.load(self.model_file)
            except:
                self.model = None

    def _save_model(self):
        if self.model:
            try:
                import joblib
                joblib.dump(self.model, self.model_file)
            except:
                pass

    def extract_features(self, indicators):
        if not indicators:
            return None
        return [
            indicators.get("rsi", 50),
            indicators.get("sk", 50),
            indicators.get("sd", 50),
            indicators.get("bb_pct", 0.5),
            indicators.get("hist", 0),
            indicators.get("hist_prev", 0),
            indicators.get("ema9", 0),
            indicators.get("ema21", 0),
            indicators.get("vol_ratio", 1),
            indicators.get("price_change", 0),
            indicators.get("atr_pct", 0),
        ]

    def record_outcome(self, symbol, action, confidence, price, indicators, outcome, pnl):
        features = self.extract_features(indicators)
        if not features:
            return

        entry = {
            "time": datetime.now().isoformat(),
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "price": price,
            "features": features,
            "outcome": outcome,
            "pnl": pnl,
        }
        self.history.append(entry)
        self._save_history()

        if len(self.history) >= self.min_samples:
            self._train()

    def _train(self):
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import cross_val_score

            X = []
            y = []
            for entry in self.history:
                features = entry.get("features")
                outcome = entry.get("outcome")
                if features and outcome in ["WIN", "LOSS"]:
                    X.append(features)
                    y.append(1 if outcome == "WIN" else 0)

            if len(X) < self.min_samples:
                return

            X = np.array(X)
            y = np.array(y)

            if len(np.unique(y)) < 2:
                return

            self.model = RandomForestClassifier(
                n_estimators=50, max_depth=5, random_state=42
            )
            self.model.fit(X, y)

            scores = cross_val_score(self.model, X, y, cv=min(5, len(X)), scoring="accuracy")
            print(f"[AI] Model egitildi | Dogruluk: {scores.mean():.1%} | Ornek: {len(X)}")

            self._save_model()
        except Exception as e:
            print(f"[AI] Egitim hatasi: {e}")

    def predict(self, indicators):
        if not self.model:
            return None

        features = self.extract_features(indicators)
        if not features:
            return None

        try:
            X = np.array([features])
            proba = self.model.predict_proba(X)[0]
            win_prob = proba[1] if len(proba) > 1 else 0.5

            importances = self.model.feature_importances_ if hasattr(self.model, 'feature_importances_') else []
            feature_names = ["RSI", "StochK", "StochD", "BB%", "MACD", "MACD_Prev", "EMA9", "EMA21", "Vol", "PriceChg", "ATR%"]

            top_factors = []
            if len(importances) > 0:
                indices = np.argsort(importances)[::-1][:3]
                for i in indices:
                    if i < len(feature_names) and importances[i] > 0.05:
                        top_factors.append(feature_names[i])

            return {
                "win_probability": round(win_prob, 3),
                "confidence": round(abs(win_prob - 0.5) * 2, 3),
                "top_factors": top_factors,
                "model_samples": len(self.history),
                "prediction": "BUY" if win_prob > 0.55 else "SELL" if win_prob < 0.45 else "HOLD"
            }
        except Exception as e:
            print(f"[AI] Tahmin hatasi: {e}")
            return None

    def get_stats(self):
        if not self.history:
            return {"total": 0, "win_rate": 0, "wins": 0, "losses": 0, "model_ready": False}

        outcomes = [h for h in self.history if h.get("outcome") in ["WIN", "LOSS"]]
        wins = sum(1 for h in outcomes if h["outcome"] == "WIN")
        losses = sum(1 for h in outcomes if h["outcome"] == "LOSS")
        total_pnl = sum(h.get("pnl", 0) for h in self.history)

        return {
            "total": len(outcomes),
            "win_rate": round(wins / len(outcomes) * 100, 1) if outcomes else 0,
            "wins": wins,
            "losses": losses,
            "total_pnl": round(total_pnl, 4),
            "model_ready": self.model is not None,
            "model_samples": len(self.history),
        }

    def should_avoid(self, symbol):
        recent = [h for h in self.history[-20:] if h.get("symbol") == symbol and h.get("outcome")]
        if len(recent) < 3:
            return False, ""
        losses = sum(1 for h in recent if h["outcome"] == "LOSS")
        if losses >= 3:
            return True, f"AI: {symbol} son {len(recent)} islemde {losses} kez zarar"
        return False, ""


ai_engine = AIEngine()
