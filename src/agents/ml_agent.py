import numpy as np
import pandas as pd
import json
import os
from datetime import datetime


class MLAgent:
    name = "AI_ML"
    icon = "brain"

    def __init__(self):
        self.model_file = "ml_model.json"
        self.history_file = "ml_history.json"
        self.weights_file = "ml_weights.json"
        self.model = None
        self.history = self._load_history()
        self.weights = self._load_weights()
        self.min_samples = 15
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

    def _load_weights(self):
        if os.path.exists(self.weights_file):
            try:
                with open(self.weights_file, "r") as f:
                    return json.load(f)
            except:
                return self._default_weights()
        return self._default_weights()

    def _default_weights(self):
        return {
            "rsi": {"buy_threshold": 30, "sell_threshold": 70, "weight": 1.0},
            "macd": {"weight": 1.0},
            "bb": {"weight": 0.8},
            "stoch": {"buy_threshold": 20, "sell_threshold": 80, "weight": 0.7},
            "ema": {"weight": 0.9},
            "volume": {"weight": 0.6},
            "momentum": {"weight": 0.8},
            "volatility": {"weight": 0.5},
            "support_resistance": {"weight": 0.7},
            "fibonacci": {"weight": 0.4},
            "candlestick": {"weight": 0.6},
        }

    def _save_weights(self):
        with open(self.weights_file, "w") as f:
            json.dump(self.weights, f, indent=2)

    def _try_load_model(self):
        if os.path.exists(self.model_file):
            try:
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

    def analyze(self, df, symbol=None):
        if len(df) < 30:
            return {"direction": "NEUTRAL", "confidence": 0, "reason": "Yetersiz veri"}

        try:
            indicators = self._extract_indicators(df)
            features = self._indicators_to_features(indicators)

            if self.model:
                prediction = self._predict_with_model(features)
                if prediction:
                    return prediction

            return self._rule_based_analysis(indicators)

        except Exception as e:
            return {"direction": "NEUTRAL", "confidence": 0, "reason": f"ML hata: {str(e)[:50]}"}

    def _extract_indicators(self, df):
        import ta

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        rsi_prev = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-2]

        stoch = ta.momentum.StochRSIIndicator(close, window=14)
        sk = stoch.stochrsi_k().iloc[-1] * 100
        sd = stoch.stochrsi_d().iloc[-1] * 100

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_pct = bb.bollinger_pband().iloc[-1]
        bb_width = (bb.bollinger_hband().iloc[-1] - bb.bollinger_lband().iloc[-1]) / bb.bollinger_mavg().iloc[-1]

        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        hist = macd.macd_diff().iloc[-1]
        hist_prev = macd.macd_diff().iloc[-2] if len(close) > 1 else 0
        macd_line = macd.macd().iloc[-1]
        signal_line = macd.macd_signal().iloc[-1]

        ema9 = ta.trend.EMAIndicator(close, window=9).ema_indicator().iloc[-1]
        ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
        ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1] if len(close) > 50 else ema21
        ema200 = ta.trend.EMAIndicator(close, window=200).ema_indicator().iloc[-1] if len(close) > 200 else ema50

        adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
        adx = adx_ind.adx().iloc[-1]
        plus_di = adx_ind.adx_pos().iloc[-1]
        minus_di = adx_ind.adx_neg().iloc[-1]

        atr = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range().iloc[-1]
        atr_pct = atr / close.iloc[-1] if close.iloc[-1] > 0 else 0

        vol_sma20 = volume.rolling(20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_sma20 if vol_sma20 > 0 else 1

        obv = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        obv_sma = obv.rolling(20).mean().iloc[-1]
        obv_trend = 1 if obv.iloc[-1] > obv.iloc[-5] else -1

        mfi = ta.volume.MFIMoneyFlowIndex(high, low, close, volume, window=14).money_flow_index().iloc[-1]

        price = close.iloc[-1]
        price_change_5 = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] if close.iloc[-5] > 0 else 0
        price_change_10 = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] if close.iloc[-10] > 0 else 0
        price_change_20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] if close.iloc[-20] > 0 else 0

        volatility = close.pct_change().rolling(20).std().iloc[-1]

        return {
            "rsi": rsi if not np.isnan(rsi) else 50,
            "rsi_prev": rsi_prev if not np.isnan(rsi_prev) else 50,
            "sk": sk if not np.isnan(sk) else 50,
            "sd": sd if not np.isnan(sd) else 50,
            "bb_pct": bb_pct if not np.isnan(bb_pct) else 0.5,
            "bb_width": bb_width if not np.isnan(bb_width) else 0,
            "hist": hist if not np.isnan(hist) else 0,
            "hist_prev": hist_prev if not np.isnan(hist_prev) else 0,
            "macd_line": macd_line if not np.isnan(macd_line) else 0,
            "signal_line": signal_line if not np.isnan(signal_line) else 0,
            "ema9": ema9,
            "ema21": ema21,
            "ema50": ema50,
            "ema200": ema200,
            "adx": adx if not np.isnan(adx) else 0,
            "plus_di": plus_di if not np.isnan(plus_di) else 0,
            "minus_di": minus_di if not np.isnan(minus_di) else 0,
            "atr_pct": atr_pct,
            "vol_ratio": vol_ratio,
            "obv_trend": obv_trend,
            "mfi": mfi if not np.isnan(mfi) else 50,
            "price": price,
            "price_change_5": price_change_5,
            "price_change_10": price_change_10,
            "price_change_20": price_change_20,
            "volatility": volatility if not np.isnan(volatility) else 0,
        }

    def _indicators_to_features(self, ind):
        return [
            ind["rsi"], ind["sk"], ind["sd"], ind["bb_pct"], ind["bb_width"],
            ind["hist"], ind["hist_prev"], ind["ema9"], ind["ema21"], ind["ema50"],
            ind["adx"], ind["plus_di"], ind["minus_di"], ind["atr_pct"],
            ind["vol_ratio"], ind["mfi"], ind["price_change_5"], ind["price_change_10"],
            ind["price_change_20"], ind["volatility"],
        ]

    def _predict_with_model(self, features):
        try:
            import numpy as np
            X = np.array([features])
            proba = self.model.predict_proba(X)[0]
            win_prob = proba[1] if len(proba) > 1 else 0.5

            importances = self.model.feature_importances_ if hasattr(self.model, 'feature_importances_') else []
            feature_names = [
                "RSI", "StochK", "StochD", "BB%", "BB_Width",
                "MACD", "MACD_Prev", "EMA9", "EMA21", "EMA50",
                "ADX", "+DI", "-DI", "ATR%",
                "Vol", "MFI", "Price5", "Price10", "Price20", "Volatility"
            ]

            top_factors = []
            if len(importances) > 0:
                indices = np.argsort(importances)[::-1][:5]
                for i in indices:
                    if i < len(feature_names) and importances[i] > 0.03:
                        top_factors.append(feature_names[i])

            if win_prob > 0.58:
                direction = "BUY"
                confidence = min((win_prob - 0.5) * 2.5, 1.0)
            elif win_prob < 0.42:
                direction = "SELL"
                confidence = min((0.5 - win_prob) * 2.5, 1.0)
            else:
                direction = "NEUTRAL"
                confidence = abs(win_prob - 0.5) * 2

            reason_parts = []
            if top_factors:
                reason_parts.append(f"Guclu: {', '.join(top_factors[:3])}")
            reason_parts.append(f"Kazanma: %{win_prob*100:.1f}")

            return {
                "direction": direction,
                "confidence": confidence,
                "reason": f"ML: {'; '.join(reason_parts)}",
                "win_probability": win_prob,
                "top_factors": top_factors
            }
        except Exception as e:
            return None

    def _rule_based_analysis(self, ind):
        buy = 0
        sell = 0
        reasons = []

        rsi_w = self.weights["rsi"]["weight"]
        if ind["rsi"] < self.weights["rsi"]["buy_threshold"]:
            buy += 0.3 * rsi_w
            reasons.append(f"RSI asiri satim ({ind['rsi']:.0f})")
        elif ind["rsi"] > self.weights["rsi"]["sell_threshold"]:
            sell += 0.3 * rsi_w
            reasons.append(f"RSI asiri alim ({ind['rsi']:.0f})")

        if ind["rsi"] < ind["rsi_prev"] and ind["rsi"] < 35:
            buy += 0.1 * rsi_w
            reasons.append("RSI toparliyor")
        elif ind["rsi"] > ind["rsi_prev"] and ind["rsi"] > 65:
            sell += 0.1 * rsi_w
            reasons.append("RSI duser")

        macd_w = self.weights["macd"]["weight"]
        if ind["hist"] > 0 and ind["hist_prev"] <= 0:
            buy += 0.25 * macd_w
            reasons.append("MACD altin kesisim")
        elif ind["hist"] < 0 and ind["hist_prev"] >= 0:
            sell += 0.25 * macd_w
            reasons.append("MACD olum kesisim")
        elif ind["hist"] > 0 and ind["hist"] > ind["hist_prev"]:
            buy += 0.1 * macd_w
        elif ind["hist"] < 0 and ind["hist"] < ind["hist_prev"]:
            sell += 0.1 * macd_w

        bb_w = self.weights["bb"]["weight"]
        if ind["bb_pct"] < 0:
            buy += 0.2 * bb_w
            reasons.append("BB altinda")
        elif ind["bb_pct"] > 1:
            sell += 0.2 * bb_w
            reasons.append("BB ustunde")

        stoch_w = self.weights["stoch"]["weight"]
        if ind["sk"] < self.weights["stoch"]["buy_threshold"] and ind["sd"] < self.weights["stoch"]["buy_threshold"]:
            buy += 0.15 * stoch_w
            reasons.append("Stoch asiri satim")
        elif ind["sk"] > self.weights["stoch"]["sell_threshold"] and ind["sd"] > self.weights["stoch"]["sell_threshold"]:
            sell += 0.15 * stoch_w
            reasons.append("Stoch asiri alim")

        ema_w = self.weights["ema"]["weight"]
        if ind["ema9"] > ind["ema21"] > ind["ema50"]:
            buy += 0.2 * ema_w
            reasons.append("EMA sirali yukari")
        elif ind["ema9"] < ind["ema21"] < ind["ema50"]:
            sell += 0.2 * ema_w
            reasons.append("EMA sirali asagi")

        vol_w = self.weights["volume"]["weight"]
        if ind["vol_ratio"] > 2:
            if ind["price_change_5"] > 0:
                buy += 0.15 * vol_w
                reasons.append(f"Hacimli yukselis ({ind['vol_ratio']:.1f}x)")
            else:
                sell += 0.15 * vol_w
                reasons.append(f"Hacimli dusus ({ind['vol_ratio']:.1f}x)")

        if ind["mfi"] < 20:
            buy += 0.2 * vol_w
            reasons.append(f"MFI asiri satim ({ind['mfi']:.0f})")
        elif ind["mfi"] > 80:
            sell += 0.2 * vol_w
            reasons.append(f"MFI asiri alim ({ind['mfi']:.0f})")

        mom_w = self.weights["momentum"]["weight"]
        if ind["adx"] > 25:
            if ind["plus_di"] > ind["minus_di"]:
                buy += 0.2 * mom_w
                reasons.append(f"Guclu trend (ADX:{ind['adx']:.0f})")
            else:
                sell += 0.2 * mom_w
                reasons.append(f"Guclu trend asagi (ADX:{ind['adx']:.0f})")

        buy = min(buy, 1.0)
        sell = min(sell, 1.0)

        if buy > sell and buy > 0.3:
            return {"direction": "BUY", "confidence": buy, "reason": "; ".join(reasons)}
        elif sell > buy and sell > 0.3:
            return {"direction": "SELL", "confidence": sell, "reason": "; ".join(reasons)}
        return {"direction": "NEUTRAL", "confidence": max(buy, sell), "reason": "ML nötr"}

    def record_outcome(self, symbol, action, confidence, price, indicators, outcome, pnl):
        features = self._indicators_to_features(indicators) if isinstance(indicators, dict) and "rsi" in indicators else None
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
            from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
            from sklearn.model_selection import cross_val_score
            from sklearn.preprocessing import StandardScaler
            import numpy as np

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

            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.1,
                random_state=42
            )
            self.model.fit(X, y)

            scores = cross_val_score(self.model, X, y, cv=min(5, len(X)), scoring="accuracy")
            print(f"[ML] Model egitildi | Dogruluk: {scores.mean():.1%} | Ornek: {len(X)}")

            self._save_model()
            self._update_weights(X, y)

        except Exception as e:
            print(f"[ML] Egitim hatasi: {e}")

    def _update_weights(self, X, y):
        try:
            import numpy as np

            feature_names = [
                "rsi", "sk", "sd", "bb", "bb_width",
                "macd", "macd_prev", "ema9", "ema21", "ema50",
                "adx", "plus_di", "minus_di", "atr",
                "vol", "mfi", "price5", "price10", "price20", "volatility"
            ]

            importances = self.model.feature_importances_

            for i, name in enumerate(feature_names):
                if i < len(importances) and name in self.weights:
                    old_w = self.weights[name]["weight"]
                    new_w = 0.3 + importances[i] * 2
                    self.weights[name]["weight"] = round(old_w * 0.7 + new_w * 0.3, 3)

            self._save_weights()
        except:
            pass

    def get_stats(self):
        if not self.history:
            return {"total": 0, "win_rate": 0, "wins": 0, "losses": 0, "model_ready": False, "accuracy": 0}

        outcomes = [h for h in self.history if h.get("outcome") in ["WIN", "LOSS"]]
        wins = sum(1 for h in outcomes if h["outcome"] == "WIN")
        losses = sum(1 for h in outcomes if h["outcome"] == "LOSS")
        total_pnl = sum(h.get("pnl", 0) for h in self.history)

        accuracy = 0
        if self.model and len(outcomes) >= 10:
            try:
                X = []
                y = []
                for entry in self.history[-100:]:
                    features = entry.get("features")
                    outcome = entry.get("outcome")
                    if features and outcome in ["WIN", "LOSS"]:
                        X.append(features)
                        y.append(1 if outcome == "WIN" else 0)
                if len(X) >= 10:
                    X = np.array(X)
                    y = np.array(y)
                    accuracy = self.model.score(X, y)
            except:
                pass

        return {
            "total": len(outcomes),
            "win_rate": round(wins / len(outcomes) * 100, 1) if outcomes else 0,
            "wins": wins,
            "losses": losses,
            "total_pnl": round(total_pnl, 4),
            "model_ready": self.model is not None,
            "model_samples": len(self.history),
            "accuracy": round(accuracy, 3),
        }


ml_agent = MLAgent()
