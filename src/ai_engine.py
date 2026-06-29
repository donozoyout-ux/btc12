import json
import os
import glob
import numpy as np
import pandas as pd
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
        self.load_kaggle_data()

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

    def load_kaggle_data(self):
        csv_files = [
            r"C:\Users\PC\Downloads\bitcoin_history.csv",
            r"C:\Users\PC\Downloads\BTC-EUR.csv",
        ]

        historical_count = 0
        for csv_path in csv_files:
            if not os.path.exists(csv_path):
                continue
            try:
                df = pd.read_csv(csv_path)
                df.columns = [c.strip().lower() for c in df.columns]

                col_map = {}
                for c in df.columns:
                    if c in ['close', 'price', 'schlusskurs', 'schluss']:
                        col_map['close'] = c
                    elif c in ['open', 'offnung', 'offnungspreis']:
                        col_map['open'] = c
                    elif c in ['high', 'hoch', 'höchstpreis']:
                        col_map['high'] = c
                    elif c in ['low', 'tief', 'tiefstpreis']:
                        col_map['low'] = c
                    elif c in ['volume', 'volumen']:
                        col_map['volume'] = c

                if 'close' not in col_map:
                    continue

                for key, col in col_map.items():
                    df[key] = pd.to_numeric(
                        df[col].astype(str).str.replace(',', '').str.replace('"', ''),
                        errors='coerce'
                    )

                df = df.dropna(subset=['close'])
                if len(df) < 30:
                    continue

                if 'high' not in col_map:
                    df['high'] = df['close']
                if 'low' not in col_map:
                    df['low'] = df['close']
                if 'open' not in col_map:
                    df['open'] = df['close']
                if 'volume' not in col_map:
                    df['volume'] = 1000000

                records = self._extract_features_from_df(df)
                historical_count += len(records)

                for entry in records:
                    self.history.append(entry)

                print(f"[AI] {os.path.basename(csv_path)} yuklendi: {len(records)} ornek")

            except Exception as e:
                print(f"[AI] {os.path.basename(csv_path)} hata: {e}")

        if historical_count > 0:
            self._save_history()
            print(f"[AI] Toplam {historical_count} tarihsel ornek yuklendi")
            if len(self.history) >= self.min_samples:
                self._train()

    def _extract_features_from_df(self, df):
        records = []
        window = 20

        for i in range(window, len(df) - 10):
            try:
                window_df = df.iloc[i - window:i + 1].copy()

                close = window_df['close']
                high = window_df['high'] if 'high' in window_df else close
                low = window_df['low'] if 'low' in window_df else close

                rsi = self._calc_rsi(close, 14)
                sk, sd = self._calc_stoch(high, low, close, 14, 3)
                bb_mid = close.rolling(20).mean().iloc[-1]
                bb_std = close.rolling(20).std().iloc[-1]
                bb_pct = (close.iloc[-1] - bb_mid) / (2 * bb_std) if bb_std > 0 else 0.5

                ema9 = close.ewm(span=9).mean().iloc[-1]
                ema21 = close.ewm(span=21).mean().iloc[-1]

                macd_line = close.ewm(span=12).mean() - close.ewm(span=26).mean()
                signal_line = macd_line.ewm(span=9).mean()
                hist = (macd_line - signal_line).iloc[-1]
                hist_prev = (macd_line - signal_line).iloc[-2] if len(macd_line) > 1 else 0

                vol_ratio = 1
                if 'volume' in window_df and window_df['volume'].rolling(20).mean().iloc[-1] > 0:
                    vol_ratio = window_df['volume'].iloc[-1] / window_df['volume'].rolling(20).mean().iloc[-1]

                price_change = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] if close.iloc[-5] > 0 else 0

                tr = pd.concat([
                    high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()
                ], axis=1).max(axis=1)
                atr_pct = tr.rolling(14).mean().iloc[-1] / close.iloc[-1] if close.iloc[-1] > 0 else 0

                future_return = (close.iloc[-10] - close.iloc[-1]) / close.iloc[-1] if close.iloc[-1] > 0 else 0
                outcome = "WIN" if future_return > 0.005 else "LOSS" if future_return < -0.005 else "BREAKEVEN"

                features = [
                    rsi if not np.isnan(rsi) else 50,
                    sk if not np.isnan(sk) else 50,
                    sd if not np.isnan(sd) else 50,
                    bb_pct if not np.isnan(bb_pct) else 0.5,
                    hist if not np.isnan(hist) else 0,
                    hist_prev if not np.isnan(hist_prev) else 0,
                    ema9 if not np.isnan(ema9) else close.iloc[-1],
                    ema21 if not np.isnan(ema21) else close.iloc[-1],
                    vol_ratio,
                    price_change,
                    atr_pct if not np.isnan(atr_pct) else 0,
                ]

                records.append({
                    "time": f"historical_{i}",
                    "symbol": "BTC/USD",
                    "action": "BUY",
                    "confidence": 0,
                    "price": float(close.iloc[-1]),
                    "features": features,
                    "outcome": outcome,
                    "pnl": future_return * settings.position_size_usd,
                    "source": "kaggle"
                })
            except Exception:
                continue

        return records

    def _calc_rsi(self, close, period=14):
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]

    def _calc_stoch(self, high, low, close, k_period=14, d_period=3):
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        k = k.fillna(50)
        d = k.rolling(window=d_period).mean().fillna(50)
        return k.iloc[-1], d.iloc[-1]

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

    def should_avoid(self, symbol):
        recent = [h for h in self.history[-20:] if h.get("symbol") == symbol and h.get("outcome")]
        if len(recent) < 3:
            return False, ""
        losses = sum(1 for h in recent if h["outcome"] == "LOSS")
        if losses >= 3:
            return True, f"AI: {symbol} son {len(recent)} islemde {losses} kez zarar"
        return False, ""


ai_engine = AIEngine()
