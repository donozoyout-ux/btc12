import numpy as np
import pickle
import os
import statistics
from datetime import datetime
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split


class AIModel:
    def __init__(self):
        self.model = XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
            use_label_encoder=False,
            eval_metric='logloss'
        )
        self.model_file = "ai_model.pkl"
        self.is_trained = False
        self.accuracy = 0.0
        self.prediction_count = 0
        self.correct_count = 0
        self._price_history = []
        self._vol_history = []
        self._load()

    def _load(self):
        if os.path.exists(self.model_file):
            try:
                with open(self.model_file, "rb") as f:
                    data = pickle.load(f)
                    self.model = data["model"]
                    self.accuracy = data.get("accuracy", 0.0)
                    self.prediction_count = data.get("prediction_count", 0)
                    self.correct_count = data.get("correct_count", 0)
                    self.is_trained = True
            except:
                pass

    def _save(self):
        with open(self.model_file, "wb") as f:
            pickle.dump({
                "model": self.model,
                "accuracy": self.accuracy,
                "prediction_count": self.prediction_count,
                "correct_count": self.correct_count,
            }, f)

    def extract_features(self, teknik, teknik_5m=None):
        features = []
        features.append(teknik.get("rsi", 50) / 100)
        features.append(teknik.get("macd_hist", 0))
        features.append(teknik.get("macd_hist_prev", 0))
        features.append(1.0 if teknik.get("ema_cross") == "bullish" else (0.0 if teknik.get("ema_cross") == "bearish" else 0.5))
        features.append(teknik.get("ema_dist", 0) / 100)
        features.append(teknik.get("bb_pct", 0.5))
        features.append(min(teknik.get("vol_ratio", 1.0), 5.0) / 5.0)
        features.append(teknik.get("atr", 0) / teknik.get("price", 60000))
        features.append(teknik.get("price_change_5", 0) / 100)
        features.append(teknik.get("breakout_up", 0))
        features.append(teknik.get("breakout_down", 0))
        ob = teknik.get("orderbook", {})
        features.append(min(ob.get("bid_ask_ratio", 1.0), 3.0) / 3.0)
        if teknik_5m:
            features.append(teknik_5m.get("rsi", 50) / 100)
            features.append(teknik_5m.get("macd_hist", 0))
            features.append(1.0 if teknik_5m.get("ema_cross") == "bullish" else (0.0 if teknik_5m.get("ema_cross") == "bearish" else 0.5))
            features.append(min(teknik_5m.get("vol_ratio", 1.0), 5.0) / 5.0)
            features.append(teknik_5m.get("price_change_5", 0) / 100)
        else:
            features.extend([0.5, 0.0, 0.5, 0.2, 0.0])
        return np.array(features).reshape(1, -1)

    def detect_anomaly(self, price, volume_ratio):
        is_anomaly = False
        score = 0.0
        self._price_history.append(price)
        self._vol_history.append(volume_ratio)
        if len(self._price_history) > 30:
            self._price_history.pop(0)
            self._vol_history.pop(0)
        if len(self._price_history) >= 10:
            price_mean = statistics.mean(self._price_history)
            price_std = statistics.stdev(self._price_history) or 1
            vol_mean = statistics.mean(self._vol_history)
            vol_std = statistics.stdev(self._vol_history) or 0.1
            price_z = abs(price - price_mean) / price_std
            vol_z = abs(volume_ratio - vol_mean) / vol_std
            if price_z > 2.5 or vol_z > 3.0:
                is_anomaly = True
                score = max(price_z / 5, vol_z / 5)
        return {"is_anomaly": is_anomaly, "anomaly_score": round(score, 2)}

    def predict(self, teknik, teknik_5m=None):
        if not teknik or "price" not in teknik:
            return 0.5, 0.0
        features = self.extract_features(teknik, teknik_5m)
        prob = 0.5
        conf = 0.0
        if self.is_trained:
            try:
                prob = float(self.model.predict_proba(features)[0][1])
                conf = abs(prob - 0.5) * 2
            except:
                prob = 0.5
                conf = 0.0
        return prob, conf

    def train(self, df, teknik_list, teknik_list_5m=None):
        if df is None or df.empty or len(teknik_list) < 20:
            return False
        try:
            X_list = []
            y_list = []
            prices = df["close"].values
            for i in range(len(teknik_list) - 1):
                t = teknik_list[i]
                t5 = teknik_list_5m[i] if teknik_list_5m and i < len(teknik_list_5m) else None
                features = self.extract_features(t, t5)
                X_list.append(features[0])
                future_return = (prices[i + 1] - prices[i]) / prices[i] * 100
                y_list.append(1 if future_return > 0.15 else 0)
            if len(X_list) < 10:
                return False
            X = np.array(X_list)
            y = np.array(y_list)
            if len(np.unique(y)) < 2:
                return False
            self.model.fit(X, y)
            self.is_trained = True
            y_pred = self.model.predict(X)
            self.accuracy = float(np.mean(y_pred == y))
            self._save()
            return True
        except:
            return False

    def record_result(self, predicted_prob, actual_return):
        self.prediction_count += 1
        predicted_direction = 1 if predicted_prob > 0.5 else 0
        actual_direction = 1 if actual_return > 0 else 0
        if predicted_direction == actual_direction:
            self.correct_count += 1
        self.accuracy = self.correct_count / max(self.prediction_count, 1)
        self._save()

    def get_state(self):
        return {
            "is_trained": self.is_trained,
            "accuracy": round(self.accuracy, 3),
            "prediction_count": self.prediction_count,
            "correct_count": self.correct_count,
        }


ai_model = AIModel()
