"""
5 Uzman AI Ajanı - Multi-Agent Consensus System
Her ajan kendi ML modeli, kendi indikatör seti ve kendi karar mantığına sahiptir.
Tüm ajanlar BaseAgent'tan türer ve analyze() metodu ile BUY/SELL/HOLD + güven puanı döner.
"""

import numpy as np
import pickle
import os
import json
from datetime import datetime

from src.config import settings

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import StandardScaler


# ---------------------------------------------------------------------------
#  Base Agent
# ---------------------------------------------------------------------------
class BaseAgent:
    """Tüm uzman ajanların temel sınıfı."""

    name = "base"
    description = "Temel Ajan"

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.accuracy = 0.0
        self.total_predictions = 0
        self.correct_predictions = 0
        self.weight = 1.0          # Konsensüs oylama ağırlığı
        self._memory_X = []
        self._memory_y = []

    # --- Alt sınıflar override eder ---
    def extract_features(self, teknik):
        raise NotImplementedError

    def _create_model(self):
        raise NotImplementedError

    # --- Ortak predict ---
    def predict(self, teknik):
        """
        Returns (action, confidence)
          action:     'BUY' | 'SELL' | 'HOLD'
          confidence: 0.0 – 1.0
        """
        features = self.extract_features(teknik)
        if features is None:
            return "HOLD", 0.0

        # Kural tabanlı ön filtre (alt sınıf override edebilir)
        rule_action, rule_conf = self.rule_based_signal(teknik)

        if not self.is_trained:
            return rule_action, rule_conf * 0.6  # Model eğitilmemişse kural güvenini düşür

        try:
            X = np.array(features).reshape(1, -1)
            if hasattr(self.scaler, 'mean_') and self.scaler.mean_ is not None:
                X = self.scaler.transform(X)
            prob = self.model.predict_proba(X)[0]
            # prob[0] = SELL, prob[1] = HOLD, prob[2] = BUY  (sınıf sırasına göre)
            classes = list(self.model.classes_)

            buy_prob = prob[classes.index(2)] if 2 in classes else 0.0
            sell_prob = prob[classes.index(0)] if 0 in classes else 0.0
            hold_prob = prob[classes.index(1)] if 1 in classes else 0.0

            # ML tahmini ile kural tabanlı sinyali birleştir
            ml_action = "HOLD"
            ml_conf = hold_prob
            if buy_prob > sell_prob and buy_prob > hold_prob:
                ml_action = "BUY"
                ml_conf = buy_prob
            elif sell_prob > buy_prob and sell_prob > hold_prob:
                ml_action = "SELL"
                ml_conf = sell_prob

            # Ağırlıklı birleştirme: %60 ML + %40 Kural
            if ml_action == rule_action:
                final_conf = ml_conf * 0.6 + rule_conf * 0.4
                return ml_action, min(final_conf, 1.0)
            elif rule_conf > 0.7:
                # Kural çok güçlüyse kuralı tercih et
                return rule_action, rule_conf * 0.7
            else:
                return ml_action, ml_conf * 0.5

        except Exception as e:
            print(f"[{self.name}] Predict hatası: {e}")
            return rule_action, rule_conf * 0.5

    def rule_based_signal(self, teknik):
        """Alt sınıflar kendi kural tabanlı sinyallerini tanımlar."""
        return "HOLD", 0.0

    # --- Eğitim ---
    def train(self, training_data):
        """
        training_data: list of (teknik_dict, label)
        label: 0=SELL, 1=HOLD, 2=BUY
        """
        if len(training_data) < 30:
            print(f"[{self.name}] Egitim iptal: Veri sayisi yetersiz ({len(training_data)} < 30)")
            return False

        try:
            X_list = []
            y_list = []
            for teknik, label in training_data:
                feat = self.extract_features(teknik)
                if feat is not None:
                    X_list.append(feat)
                    y_list.append(label)

            if len(X_list) < 20:
                print(f"[{self.name}] Egitim iptal: Gecerli ozellik cikarilan veri sayisi az ({len(X_list)} < 20)")
                return False

            X = np.array(X_list)
            y = np.array(y_list)

            # Bellek ile birleştir
            if len(self._memory_X) > 0:
                X = np.vstack([np.array(self._memory_X[-500:]), X])
                y = np.hstack([np.array(self._memory_y[-500:]), y])

            # En az 2 sınıf gerekli
            unique_classes = np.unique(y)
            if len(unique_classes) < 2:
                print(f"[{self.name}] Egitim iptal: Yetersiz sinif sayisi (Sadece {unique_classes} var, en az 2 gerekli)")
                return False

            self.scaler.fit(X)
            X_scaled = self.scaler.transform(X)

            if self.model is None:
                self.model = self._create_model()

            self.model.fit(X_scaled, y)
            self.is_trained = True

            # Doğruluk hesapla
            y_pred = self.model.predict(X_scaled)
            self.accuracy = float(np.mean(y_pred == y))

            # Belleğe ekle
            self._memory_X.extend(X_list)
            self._memory_y.extend(y_list)
            if len(self._memory_X) > 1000:
                self._memory_X = self._memory_X[-1000:]
                self._memory_y = self._memory_y[-1000:]

            print(f"[{self.name}] Eğitildi: {len(X)} örnek, doğruluk=%{self.accuracy*100:.0f}")
            return True
        except Exception as e:
            print(f"[{self.name}] Eğitim hatası: {e}")
            import traceback
            traceback.print_exc()
            return False

    def record_result(self, predicted_action, actual_profitable):
        """İşlem sonucunu kaydet ve ağırlığı güncelle."""
        self.total_predictions += 1
        if actual_profitable:
            self.correct_predictions += 1
        if self.total_predictions >= 5:
            acc = self.correct_predictions / self.total_predictions
            if acc > 0.6:
                self.weight = min(2.0, self.weight * 1.05)
            elif acc < 0.35:
                self.weight = max(0.3, self.weight * 0.95)

    def get_state(self):
        return {
            "name": self.name,
            "description": self.description,
            "is_trained": self.is_trained,
            "accuracy": round(self.accuracy, 3),
            "weight": round(self.weight, 3),
            "total_predictions": self.total_predictions,
            "correct_predictions": self.correct_predictions,
            "memory_size": len(self._memory_X),
        }

    def load_state(self, state_dict):
        """Supabase'den yüklenen durumu geri yükle."""
        if not state_dict:
            return
        self.weight = state_dict.get("weight", 1.0)
        self.total_predictions = state_dict.get("total_predictions", 0)
        self.correct_predictions = state_dict.get("correct_predictions", 0)
        self.accuracy = state_dict.get("accuracy", 0.0)


# ---------------------------------------------------------------------------
#  AJAN 1: Trend & Momentum AI (Random Forest)
# ---------------------------------------------------------------------------
class TrendAgent(BaseAgent):
    name = "trend"
    description = "Trend & Momentum AI"

    def _create_model(self):
        return RandomForestClassifier(
            n_estimators=80, max_depth=6, random_state=42, n_jobs=-1
        )

    def extract_features(self, teknik):
        if not teknik or "price" not in teknik:
            return None
        try:
            ema8 = teknik.get("ema8", 0)
            ema21 = teknik.get("ema21", 0)
            price = teknik["price"]
            macd_hist = teknik.get("macd_hist", 0)
            macd_hist_prev = teknik.get("macd_hist_prev", 0)
            ema_dist = teknik.get("ema_dist", 0)
            sling_dist = teknik.get("sling_dist", 0)
            price_change_5 = teknik.get("price_change_5", 0)
            vol_ratio = teknik.get("vol_ratio", 1.0)
            atr_pct = teknik.get("atr_pct", 0)
            adx = teknik.get("adx", 0)
            di_plus = teknik.get("di_plus", 0)
            di_minus = teknik.get("di_minus", 0)
            momentum_score = teknik.get("momentum_score", 0)
            vwap_dist = teknik.get("vwap_dist", 0)
            donchian_pos = teknik.get("donchian_pos", 0.5)
            roc = teknik.get("roc", 0)

            # EMA trend gücü
            ema_trend = 1.0 if ema8 > ema21 else -1.0
            # MACD momentum
            macd_momentum = macd_hist - macd_hist_prev
            # Trend süresi (sling colors)
            sling_colors = teknik.get("sling_colors", [])
            consecutive_green = 0
            consecutive_red = 0
            for c in reversed(sling_colors):
                if c == "GREEN":
                    consecutive_green += 1
                else:
                    break
            for c in reversed(sling_colors):
                if c == "RED":
                    consecutive_red += 1
                else:
                    break

            return [
                ema_trend,
                ema_dist / 100 if abs(ema_dist) < 100 else np.sign(ema_dist),
                sling_dist / 100 if abs(sling_dist) < 100 else np.sign(sling_dist),
                macd_hist,
                macd_momentum,
                1.0 if macd_hist > 0 and macd_hist_prev <= 0 else (
                    -1.0 if macd_hist < 0 and macd_hist_prev >= 0 else 0.0),
                price_change_5 / 100,
                min(vol_ratio, 5.0) / 5.0,
                atr_pct / 100 if atr_pct < 100 else 1.0,
                min(consecutive_green, 20) / 20.0,
                min(consecutive_red, 20) / 20.0,
                min(adx, 100) / 100,
                1.0 if di_plus > di_minus else -1.0,
                momentum_score / 100,
                vwap_dist / 100 if abs(vwap_dist) < 100 else np.sign(vwap_dist),
                donchian_pos,
                roc / 100 if abs(roc) < 100 else np.sign(roc),
            ]
        except:
            return None

    def rule_based_signal(self, teknik):
        score = 0.0
        ema_cross = teknik.get("ema_cross", "")
        macd_hist = teknik.get("macd_hist", 0)
        macd_hist_prev = teknik.get("macd_hist_prev", 0)
        price_change_5 = teknik.get("price_change_5", 0)
        ema_dist = teknik.get("ema_dist", 0)

        # EMA Cross
        if ema_cross == "bullish":
            score += 0.25
        elif ema_cross == "bearish":
            score -= 0.25

        # MACD Kesişim
        if macd_hist > 0 and macd_hist_prev <= 0:
            score += 0.30
        elif macd_hist < 0 and macd_hist_prev >= 0:
            score -= 0.30
        elif macd_hist > 0 and macd_hist > macd_hist_prev:
            score += 0.15
        elif macd_hist < 0 and macd_hist < macd_hist_prev:
            score -= 0.15

        # Momentum
        if price_change_5 > 0.5:
            score += 0.15
        elif price_change_5 < -0.5:
            score -= 0.15

        # EMA mesafesi
        if -2 < ema_dist < 0 and ema_cross == "bullish":
            score += 0.15  # Pullback fırsatı
        elif 0 < ema_dist < 2 and ema_cross == "bearish":
            score -= 0.15

        if score > 0.3:
            return "BUY", min(score, 1.0)
        elif score < -0.3:
            return "SELL", min(abs(score), 1.0)
        return "HOLD", 0.1


# ---------------------------------------------------------------------------
#  AJAN 2: Volatilite & Aşırı Alım/Satım AI (SVM + KNN Ensemble)
# ---------------------------------------------------------------------------
class VolatilityAgent(BaseAgent):
    name = "volatility"
    description = "Volatilite & Mean Reversion AI"

    def __init__(self):
        super().__init__()
        self.knn_model = None

    def _create_model(self):
        # Ana model: SVM (probability=True ile)
        self.knn_model = KNeighborsClassifier(n_neighbors=7)
        return SVC(kernel='rbf', probability=True, gamma='scale', C=1.0, random_state=42)

    def train(self, training_data):
        result = super().train(training_data)
        # KNN modelini de eğit
        if result and self.knn_model is not None and len(self._memory_X) > 20:
            try:
                X = np.array(self._memory_X[-500:])
                y = np.array(self._memory_y[-500:])
                if len(np.unique(y)) >= 2:
                    X_scaled = self.scaler.transform(X)
                    self.knn_model.fit(X_scaled, y)
            except:
                pass
        return result

    def extract_features(self, teknik):
        if not teknik or "price" not in teknik:
            return None
        try:
            rsi = teknik.get("rsi", 50)
            rsi_prev = teknik.get("rsi_prev", 50)
            stoch_rsi = teknik.get("stoch_rsi", 50)
            stoch_rsi_prev = teknik.get("stoch_rsi_prev", 50)
            bb_pct = teknik.get("bb_pct", 0.5)
            atr = teknik.get("atr", 0)
            atr_pct = teknik.get("atr_pct", 0)
            price = teknik["price"]
            vol_ratio = teknik.get("vol_ratio", 1.0)
            cci = teknik.get("cci", 0)
            williams_r = teknik.get("williams_r", -50)
            mfi = teknik.get("mfi", 50)
            donchian_pos = teknik.get("donchian_pos", 0.5)

            return [
                rsi / 100,
                (rsi - rsi_prev) / 100,
                stoch_rsi / 100,
                (stoch_rsi - stoch_rsi_prev) / 100,
                bb_pct,
                atr_pct / 100 if atr_pct < 100 else 1.0,
                min(vol_ratio, 5.0) / 5.0,
                1.0 if rsi < 30 else (0.0 if rsi > 70 else 0.5),
                1.0 if stoch_rsi < 20 else (0.0 if stoch_rsi > 80 else 0.5),
                1.0 if bb_pct < 0 else (0.0 if bb_pct > 1 else bb_pct),
                cci / 100 if abs(cci) < 200 else np.sign(cci),
                williams_r / 100,
                mfi / 100,
                donchian_pos,
            ]
        except:
            return None

    def predict(self, teknik):
        """SVM ve KNN tahminlerini birleştirir."""
        features = self.extract_features(teknik)
        if features is None:
            return "HOLD", 0.0

        rule_action, rule_conf = self.rule_based_signal(teknik)

        if not self.is_trained:
            return rule_action, rule_conf * 0.6

        try:
            X = np.array(features).reshape(1, -1)
            if hasattr(self.scaler, 'mean_') and self.scaler.mean_ is not None:
                X = self.scaler.transform(X)

            # SVM tahmini
            svm_prob = self.model.predict_proba(X)[0]
            svm_classes = list(self.model.classes_)

            # KNN tahmini
            knn_prob = svm_prob  # fallback
            if self.knn_model is not None:
                try:
                    knn_prob = self.knn_model.predict_proba(X)[0]
                except:
                    pass

            # Ensemble: %50 SVM + %50 KNN
            avg_prob = {}
            for i, cls in enumerate(svm_classes):
                svm_p = svm_prob[i] if i < len(svm_prob) else 0
                knn_p = knn_prob[i] if i < len(knn_prob) else 0
                avg_prob[cls] = (svm_p + knn_p) / 2

            buy_p = avg_prob.get(2, 0)
            sell_p = avg_prob.get(0, 0)
            hold_p = avg_prob.get(1, 0)

            ml_action = "HOLD"
            ml_conf = hold_p
            if buy_p > sell_p and buy_p > hold_p:
                ml_action = "BUY"
                ml_conf = buy_p
            elif sell_p > buy_p and sell_p > hold_p:
                ml_action = "SELL"
                ml_conf = sell_p

            # Kural ile birleştir
            if ml_action == rule_action:
                return ml_action, min(ml_conf * 0.55 + rule_conf * 0.45, 1.0)
            elif rule_conf > 0.7:
                return rule_action, rule_conf * 0.65
            else:
                return ml_action, ml_conf * 0.5

        except Exception as e:
            print(f"[{self.name}] Predict hatası: {e}")
            return rule_action, rule_conf * 0.5

    def rule_based_signal(self, teknik):
        rsi = teknik.get("rsi", 50)
        stoch_rsi = teknik.get("stoch_rsi", 50)
        bb_pct = teknik.get("bb_pct", 0.5)
        score = 0.0

        # RSI aşırı bölgeleri
        if rsi < 25:
            score += 0.40
        elif rsi < 35:
            score += 0.20
        elif rsi > 75:
            score -= 0.40
        elif rsi > 65:
            score -= 0.20

        # StochRSI
        if stoch_rsi < 15:
            score += 0.30
        elif stoch_rsi > 85:
            score -= 0.30

        # Bollinger Band
        if bb_pct < 0:
            score += 0.25
        elif bb_pct < 0.1:
            score += 0.15
        elif bb_pct > 1.0:
            score -= 0.25
        elif bb_pct > 0.9:
            score -= 0.15

        if score > 0.3:
            return "BUY", min(score, 1.0)
        elif score < -0.3:
            return "SELL", min(abs(score), 1.0)
        return "HOLD", 0.1


# ---------------------------------------------------------------------------
#  AJAN 3: Hacim & Orderbook AI (Logistic Regression)
# ---------------------------------------------------------------------------
class VolumeAgent(BaseAgent):
    name = "volume"
    description = "Hacim & Orderbook AI"

    def _create_model(self):
        return LogisticRegression(max_iter=500, random_state=42, multi_class='multinomial')

    def extract_features(self, teknik):
        if not teknik or "price" not in teknik:
            return None
        try:
            vol_ratio = teknik.get("vol_ratio", 1.0)
            price_change_5 = teknik.get("price_change_5", 0)
            mfi = teknik.get("mfi", 50)
            obv_signal = teknik.get("obv_signal", 0.0)
            vwap_dist = teknik.get("vwap_dist", 0.0)

            ob = teknik.get("orderbook", {})
            ob_ratio = ob.get("bid_ask_ratio", 1.0)
            ob_sinyal = ob.get("bid_ask_sinyal", "notr")

            # Hacim teyidi: fiyat yükselip hacim de yükseliyorsa güçlü sinyal
            vol_price_confirm = 1.0 if (price_change_5 > 0 and vol_ratio > 1.3) else (
                -1.0 if (price_change_5 < 0 and vol_ratio > 1.3) else 0.0)

            return [
                min(vol_ratio, 5.0) / 5.0,
                min(ob_ratio, 3.0) / 3.0,
                1.0 if ob_sinyal == "alis_baskisi" else (-1.0 if ob_sinyal == "satis_baskisi" else 0.0),
                price_change_5 / 100,
                vol_price_confirm,
                1.0 if vol_ratio > 2.0 else (0.5 if vol_ratio > 1.5 else 0.0),
                1.0 if vol_ratio > 3.0 else 0.0,
                mfi / 100,
                obv_signal,
                vwap_dist / 100 if abs(vwap_dist) < 100 else np.sign(vwap_dist),
            ]
        except:
            return None

    def rule_based_signal(self, teknik):
        vol_ratio = teknik.get("vol_ratio", 1.0)
        price_change_5 = teknik.get("price_change_5", 0)
        ob = teknik.get("orderbook", {})
        ob_ratio = ob.get("bid_ask_ratio", 1.0)

        score = 0.0

        # Orderbook dengesizliği
        if ob_ratio > 1.5:
            score += 0.30
        elif ob_ratio > 1.2:
            score += 0.15
        elif ob_ratio < 0.6:
            score -= 0.30
        elif ob_ratio < 0.8:
            score -= 0.15

        # Hacim teyidi
        if vol_ratio > 2.0 and price_change_5 > 0:
            score += 0.25
        elif vol_ratio > 1.5 and price_change_5 > 0:
            score += 0.15
        elif vol_ratio > 2.0 and price_change_5 < 0:
            score -= 0.25
        elif vol_ratio > 1.5 and price_change_5 < 0:
            score -= 0.15

        # Hacimsiz hareket = güvenilmez
        if vol_ratio < 0.5 and abs(price_change_5) > 0.3:
            return "HOLD", 0.3  # Tuzak uyarısı

        if score > 0.25:
            return "BUY", min(score, 1.0)
        elif score < -0.25:
            return "SELL", min(abs(score), 1.0)
        return "HOLD", 0.1


# ---------------------------------------------------------------------------
#  AJAN 4: Kırılım & Destek/Direnç AI (Decision Tree + Gradient Boosting)
# ---------------------------------------------------------------------------
class LevelAgent(BaseAgent):
    name = "level"
    description = "Kırılım & Seviye AI"

    def _create_model(self):
        return GradientBoostingClassifier(
            n_estimators=60, max_depth=4, learning_rate=0.1, random_state=42
        )

    def extract_features(self, teknik):
        if not teknik or "price" not in teknik:
            return None
        try:
            price = teknik["price"]
            support = teknik.get("support", price)
            resistance = teknik.get("resistance", price)
            breakout_up = teknik.get("breakout_up", 0)
            breakout_down = teknik.get("breakout_down", 0)
            bb_upper = teknik.get("bb_upper", price)
            bb_lower = teknik.get("bb_lower", price)
            atr = teknik.get("atr", 0)
            vol_ratio = teknik.get("vol_ratio", 1.0)
            donchian_pos = teknik.get("donchian_pos", 0.5)
            vwap_dist = teknik.get("vwap_dist", 0.0)

            # Fiyatın destek/direnç arasındaki konumu
            sr_range = resistance - support if resistance > support else 1
            price_position = (price - support) / sr_range  # 0=destek, 1=direnç

            # BB içindeki konum
            bb_range = bb_upper - bb_lower if bb_upper > bb_lower else 1
            bb_position = (price - bb_lower) / bb_range

            # Destek/dirence uzaklık (ATR cinsinden)
            dist_to_support = (price - support) / atr if atr > 0 else 0
            dist_to_resistance = (resistance - price) / atr if atr > 0 else 0

            return [
                price_position,
                bb_position,
                breakout_up,
                breakout_down,
                min(dist_to_support, 5) / 5,
                min(dist_to_resistance, 5) / 5,
                min(vol_ratio, 5.0) / 5.0,
                atr / price if price > 0 else 0,
                1.0 if price_position < 0.2 else 0.0,
                1.0 if price_position > 0.8 else 0.0,
                donchian_pos,
                vwap_dist / 100 if abs(vwap_dist) < 100 else np.sign(vwap_dist),
            ]
        except:
            return None

    def rule_based_signal(self, teknik):
        breakout_up = teknik.get("breakout_up", 0)
        breakout_down = teknik.get("breakout_down", 0)
        price = teknik.get("price", 0)
        support = teknik.get("support", 0)
        resistance = teknik.get("resistance", 0)
        vol_ratio = teknik.get("vol_ratio", 1.0)
        bb_pct = teknik.get("bb_pct", 0.5)

        score = 0.0

        # Kırılım sinyalleri
        if breakout_up > 0:
            score += 0.40
        if breakout_down > 0:
            score -= 0.40

        # Destek bölgesinde alım
        if support > 0 and resistance > support:
            pos = (price - support) / (resistance - support)
            if pos < 0.15:
                score += 0.25  # Destek yakını
            elif pos > 0.85:
                score -= 0.25  # Direnç yakını

        # Hacim teyidi
        if vol_ratio > 1.5 and (breakout_up > 0 or breakout_down > 0):
            score += 0.15 * np.sign(score) if score != 0 else 0

        if score > 0.25:
            return "BUY", min(score, 1.0)
        elif score < -0.25:
            return "SELL", min(abs(score), 1.0)
        return "HOLD", 0.1


# ---------------------------------------------------------------------------
#  AJAN 5: Duygu & Haber AI (VaderSentiment NLP)
# ---------------------------------------------------------------------------
class SentimentAgent(BaseAgent):
    name = "sentiment"
    description = "Duygu & Haber AI"

    def __init__(self):
        super().__init__()
        self._vader = None
        self._fear_greed = 50  # Nötr başlangıç
        self._last_sentiment_score = 0.0
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._vader = SentimentIntensityAnalyzer()
            print("[SENTIMENT] VaderSentiment NLP yuklendi")
        except ImportError:
            print("[SENTIMENT] VaderSentiment yüklenemedi, kural tabanlı çalışacak")

    def _create_model(self):
        return DecisionTreeClassifier(max_depth=5, random_state=42)

    def extract_features(self, teknik):
        """Sentiment ajanı teknik veriden ziyade haberlere odaklanır."""
        if not teknik:
            return None
        try:
            # Teknik verileri de sentiment bağlamında kullanıyoruz
            rsi = teknik.get("rsi", 50)
            vol_ratio = teknik.get("vol_ratio", 1.0)
            price_change_5 = teknik.get("price_change_5", 0)
            momentum_score = teknik.get("momentum_score", 0)
            adx = teknik.get("adx", 0)

            return [
                self._last_sentiment_score,
                self._fear_greed / 100,
                rsi / 100,
                min(vol_ratio, 5.0) / 5.0,
                price_change_5 / 100,
                momentum_score / 100,
                min(adx, 100) / 100,
                1.0 if self._last_sentiment_score > 0.3 else 0.0,
                1.0 if self._last_sentiment_score < -0.3 else 0.0,
            ]
        except:
            return None

    def analyze_news(self, haberler):
        """Haber başlıklarını VaderSentiment ile analiz et."""
        if not haberler:
            self._last_sentiment_score = 0.0
            return

        total_score = 0.0
        count = 0

        for haber in haberler:
            baslik = haber.get("baslik", "")
            if not baslik:
                continue

            if self._vader:
                scores = self._vader.polarity_scores(baslik)
                total_score += scores["compound"]
            else:
                # Fallback: basit kelime bazlı analiz
                text_lower = baslik.lower()
                pos_words = ["rally", "surge", "bull", "soar", "gain", "rise", "record", "high", "pump", "moon", "up"]
                neg_words = ["crash", "dump", "bear", "fall", "drop", "low", "hack", "ban", "sec", "fraud", "sell"]
                for w in pos_words:
                    if w in text_lower:
                        total_score += 0.15
                for w in neg_words:
                    if w in text_lower:
                        total_score -= 0.15
            count += 1

        self._last_sentiment_score = total_score / max(count, 1)

    def update_fear_greed(self, index_value):
        """Fear & Greed index güncelle (0-100)."""
        if index_value is not None:
            self._fear_greed = max(0, min(100, index_value))

    def predict(self, teknik, haberler=None):
        """Sentiment ajanı haberlerle birlikte tahmin yapar."""
        if haberler:
            self.analyze_news(haberler)

        features = self.extract_features(teknik)
        if features is None:
            return "HOLD", 0.0

        rule_action, rule_conf = self.rule_based_signal(teknik)

        if not self.is_trained:
            return rule_action, rule_conf * 0.6

        try:
            X = np.array(features).reshape(1, -1)
            if hasattr(self.scaler, 'mean_') and self.scaler.mean_ is not None:
                X = self.scaler.transform(X)
            prob = self.model.predict_proba(X)[0]
            classes = list(self.model.classes_)

            buy_p = prob[classes.index(2)] if 2 in classes else 0
            sell_p = prob[classes.index(0)] if 0 in classes else 0

            ml_action = "HOLD"
            ml_conf = 0.3
            if buy_p > sell_p and buy_p > 0.4:
                ml_action = "BUY"
                ml_conf = buy_p
            elif sell_p > buy_p and sell_p > 0.4:
                ml_action = "SELL"
                ml_conf = sell_p

            if ml_action == rule_action:
                return ml_action, min(ml_conf * 0.5 + rule_conf * 0.5, 1.0)
            elif rule_conf > 0.6:
                return rule_action, rule_conf * 0.7
            return ml_action, ml_conf * 0.5

        except:
            return rule_action, rule_conf * 0.5

    def rule_based_signal(self, teknik):
        s = self._last_sentiment_score
        fg = self._fear_greed

        score = 0.0

        # Sentiment skoru
        if s > 0.5:
            score += 0.35
        elif s > 0.2:
            score += 0.15
        elif s < -0.5:
            score -= 0.40  # Olumsuz haberlerde daha agresif
        elif s < -0.2:
            score -= 0.20

        # Fear & Greed
        if fg < 20:  # Extreme fear = contrarian buy
            score += 0.20
        elif fg < 35:
            score += 0.10
        elif fg > 80:  # Extreme greed = contrarian sell
            score -= 0.20
        elif fg > 65:
            score -= 0.10

        if score > 0.2:
            return "BUY", min(score, 1.0)
        elif score < -0.2:
            return "SELL", min(abs(score), 1.0)
        return "HOLD", 0.1

    def get_state(self):
        state = super().get_state()
        state["last_sentiment"] = round(self._last_sentiment_score, 3)
        state["fear_greed"] = self._fear_greed
        return state


# ---------------------------------------------------------------------------
#  Konsensüs Koordinatörü
# ---------------------------------------------------------------------------
class ConsensusCoordinator:
    """5 uzman ajanın oylarını toplar ve nihai kararı verir."""

    def __init__(self):
        self.agents = {
            "trend": TrendAgent(),
            "volatility": VolatilityAgent(),
            "volume": VolumeAgent(),
            "level": LevelAgent(),
            "sentiment": SentimentAgent(),
        }
        self.min_consensus = 3       # En az 3 ajan aynı yönde olmalı
        self.min_weighted_conf = 0.45  # Ağırlıklı minimum güven
        self.last_votes = {}          # Son oylar (panel'de göstermek için)
        self.total_decisions = 0
        self.consensus_reached = 0

    def vote(self, teknik, haberler=None, gemini=None):
        """
        Tüm ajanlardan oy topla.
        Returns: {
            "action": "BUY"|"SELL"|"HOLD",
            "confidence": 0.0-1.0,
            "votes": {agent_name: {"action": ..., "confidence": ...}},
            "consensus": True|False,
            "details": str
        }
        """
        votes = {}

        for name, agent in self.agents.items():
            try:
                if name == "sentiment":
                    action, conf = agent.predict(teknik, haberler)
                else:
                    action, conf = agent.predict(teknik)
                votes[name] = {"action": action, "confidence": round(conf, 3), "weight": round(agent.weight, 3)}
            except Exception as e:
                print(f"[CONSENSUS] {name} ajan hatası: {e}")
                votes[name] = {"action": "HOLD", "confidence": 0.0, "weight": agent.weight}

        self.last_votes = votes
        self.total_decisions += 1

        # Oyları say
        buy_count = sum(1 for v in votes.values() if v["action"] == "BUY")
        sell_count = sum(1 for v in votes.values() if v["action"] == "SELL")
        hold_count = sum(1 for v in votes.values() if v["action"] == "HOLD")

        # Ağırlıklı güven hesapla
        buy_weighted = sum(v["confidence"] * v["weight"] for v in votes.values() if v["action"] == "BUY")
        sell_weighted = sum(v["confidence"] * v["weight"] for v in votes.values() if v["action"] == "SELL")
        total_weight = sum(v["weight"] for v in votes.values())

        details_parts = []

        # --- Gemini 5-beyni konsensüse bağla (kullanıcının niyeti) ---
        gemini_action = None
        gemini_conf = 0.0
        if gemini and gemini.get("final_decision") in ("BUY", "SELL"):
            gemini_action = gemini["final_decision"]
            gemini_conf = float(gemini.get("final_confidence", 0) or 0)
            gw = settings.gemini_weight  # Gemini'in konsensüsteki ağırlığı (ayarlanabilir)
            if gw <= 0:
                pass  # 0 ise Gemini konsensüse etki etmez
            elif gemini_action == "BUY":
                buy_count += 1
                buy_weighted += gemini_conf * gw
            elif gemini_action == "SELL":
                sell_count += 1
                sell_weighted += gemini_conf * gw
            total_weight += gw
            details_parts.append(f"🧠gemini:{gemini_action}({gemini_conf:.0%})")

        buy_score = buy_weighted / total_weight if total_weight > 0 else 0
        sell_score = sell_weighted / total_weight if total_weight > 0 else 0

        # Konsensüs kararı
        action = "HOLD"
        confidence = 0.0
        consensus = False

        for name, v in votes.items():
            emoji = "🟢" if v["action"] == "BUY" else ("🔴" if v["action"] == "SELL" else "⚪")
            details_parts.append(f"{emoji}{name}:{v['action']}({v['confidence']:.0%})")

        details = " | ".join(details_parts)

        if buy_count >= self.min_consensus and buy_score >= self.min_weighted_conf:
            action = "BUY"
            confidence = buy_score
            consensus = True
            self.consensus_reached += 1
        elif sell_count >= self.min_consensus and sell_score >= self.min_weighted_conf:
            action = "SELL"
            confidence = sell_score
            consensus = True
            self.consensus_reached += 1

        return {
            "action": action,
            "confidence": round(confidence, 3),
            "votes": votes,
            "consensus": consensus,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "buy_score": round(buy_score, 3),
            "sell_score": round(sell_score, 3),
            "gemini": {"action": gemini_action, "confidence": round(gemini_conf, 3)},
            "details": details,
        }

    def train_all(self, training_data):
        """Tüm ajanları eğit."""
        results = {}
        for name, agent in self.agents.items():
            try:
                ok = agent.train(training_data)
                results[name] = ok
            except Exception as e:
                print(f"[CONSENSUS] {name} eğitim hatası: {e}")
                results[name] = False
        trained_count = sum(1 for v in results.values() if v)
        print(f"[CONSENSUS] Eğitim tamamlandı: {trained_count}/5 ajan eğitildi")
        return results

    def record_result_all(self, predicted_action, actual_profitable):
        """Tüm ajanlara işlem sonucunu bildir."""
        for name, agent in self.agents.items():
            v = self.last_votes.get(name, {})
            if v.get("action") == predicted_action:
                agent.record_result(predicted_action, actual_profitable)

    def get_all_states(self):
        """Panel'de göstermek için tüm ajan durumlarını döndür."""
        states = {}
        for name, agent in self.agents.items():
            states[name] = agent.get_state()
        states["_coordinator"] = {
            "total_decisions": self.total_decisions,
            "consensus_reached": self.consensus_reached,
            "consensus_rate": round(self.consensus_reached / max(self.total_decisions, 1), 3),
            "min_consensus": self.min_consensus,
        }
        states["_last_votes"] = self.last_votes
        return states

    def save_states(self):
        """Tüm ajan durumlarını ve eğitilmiş modelleri döndür (Supabase'e kaydetmek için)."""
        data = {}
        import base64
        import pickle
        for name, agent in self.agents.items():
            model_bytes = ""
            scaler_bytes = ""
            if agent.is_trained and agent.model is not None:
                try:
                    model_bytes = base64.b64encode(pickle.dumps(agent.model)).decode("utf-8")
                    scaler_bytes = base64.b64encode(pickle.dumps(agent.scaler)).decode("utf-8")
                except Exception as e:
                    print(f"[CONSENSUS] {name} serialize hatasi: {e}")
            
            data[name] = {
                "weight": agent.weight,
                "total_predictions": agent.total_predictions,
                "correct_predictions": agent.correct_predictions,
                "accuracy": agent.accuracy,
                "is_trained": agent.is_trained,
                "model_pkl": model_bytes,
                "scaler_pkl": scaler_bytes,
            }
        data["_coordinator"] = {
            "total_decisions": self.total_decisions,
            "consensus_reached": self.consensus_reached,
        }
        return data

    def load_states(self, data):
        """Supabase'den yüklenen durumları ve modelleri geri yükle."""
        if not data:
            return
        import base64
        import pickle
        for name, agent in self.agents.items():
            if name in data:
                item = data[name]
                agent.weight = item.get("weight", 1.0)
                agent.total_predictions = item.get("total_predictions", 0)
                agent.correct_predictions = item.get("correct_predictions", 0)
                agent.accuracy = item.get("accuracy", 0.0)
                agent.is_trained = item.get("is_trained", False)
                
                model_pkl = item.get("model_pkl", "")
                scaler_pkl = item.get("scaler_pkl", "")
                if model_pkl and scaler_pkl:
                    try:
                        agent.model = pickle.loads(base64.b64decode(model_pkl.encode("utf-8")))
                        agent.scaler = pickle.loads(base64.b64decode(scaler_pkl.encode("utf-8")))
                        print(f"[CONSENSUS] {name} model pkl basariyla yuklendi (Accuracy: %{agent.accuracy*100:.0f})")
                    except Exception as e:
                        print(f"[CONSENSUS] {name} model pkl yukleme hatasi: {e}")
        coord = data.get("_coordinator", {})
        self.total_decisions = coord.get("total_decisions", 0)
        self.consensus_reached = coord.get("consensus_reached", 0)
        print(f"[CONSENSUS] Ajan durumları yüklendi (karar:{self.total_decisions}, konsensüs:{self.consensus_reached})")


# Tek global instance
consensus = ConsensusCoordinator()
