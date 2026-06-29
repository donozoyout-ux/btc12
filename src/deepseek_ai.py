import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from src.config import settings
from src.trader import trader


class DeepSeekAI:
    def __init__(self):
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        self.last_decision = None

    def analyze(self, df):
        if len(df) < 50:
            return {"action": "HOLD", "confidence": 0, "reason": "Yetersiz veri"}

        if not settings.deepseek_api_key:
            return {"action": "HOLD", "confidence": 0, "reason": "DeepSeek API key yok"}

        try:
            indicators = self._calc_indicators(df)
            ob = trader.get_orderbook()
            indicators.update(ob)
            prompt = self._build_prompt(indicators)
            response = self._call_deepseek(prompt)
            return self._parse_response(response, indicators)
        except Exception as e:
            return {"action": "HOLD", "confidence": 0, "reason": f"Hata: {str(e)[:80]}"}

    def _calc_indicators(self, df):
        try:
            import pandas_ta as ta
        except ImportError:
            return self._fallback_indicators(df)

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        rsi = ta.rsi(close, length=14).iloc[-1] if ta.rsi(close, length=14) is not None else 50
        macd = ta.macd(close, fast=12, slow=26, signal=9)
        macd_line = macd['MACD_12_26_9'].iloc[-1] if macd is not None else 0
        macd_signal = macd['MACDs_12_26_9'].iloc[-1] if macd is not None else 0
        macd_hist = macd['MACDh_12_26_9'].iloc[-1] if macd is not None else 0
        bb = ta.bbands(close, length=20, std=2)
        bb_pct = bb['BBP_20_2.0'].iloc[-1] if bb is not None else 0.5
        bb_upper = bb['BBU_20_2.0'].iloc[-1] if bb is not None else close.iloc[-1]
        bb_lower = bb['BBL_20_2.0'].iloc[-1] if bb is not None else close.iloc[-1]
        ema9 = ta.ema(close, length=9).iloc[-1] if ta.ema(close, length=9) is not None else close.iloc[-1]
        ema21 = ta.ema(close, length=21).iloc[-1] if ta.ema(close, length=21) is not None else close.iloc[-1]
        ema50 = ta.ema(close, length=50).iloc[-1] if len(close) > 50 and ta.ema(close, length=50) is not None else close.iloc[-1]
        atr = ta.atr(high, low, close, length=14).iloc[-1] if ta.atr(high, low, close, length=14) is not None else 0
        obv = ta.obv(close, volume).iloc[-1] if ta.obv(close, volume) is not None else 0
        stoch = ta.stoch(high, low, close, k=14, d=3)
        stoch_k = stoch['STOCHk_14_3_3'].iloc[-1] if stoch is not None else 50
        stoch_d = stoch['STOCHd_14_3_3'].iloc[-1] if stoch is not None else 50
        adx = ta.adx(high, low, close, length=14).iloc[-1] if ta.adx(high, low, close, length=14) is not None else 0
        cci = ta.cci(high, low, close, length=20).iloc[-1] if ta.cci(high, low, close, length=20) is not None else 0
        willr = ta.willr(high, low, close, length=14).iloc[-1] if ta.willr(high, low, close, length=14) is not None else -50

        price = close.iloc[-1]
        price_change_5 = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100 if close.iloc[-5] > 0 else 0
        price_change_20 = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100 if close.iloc[-20] > 0 else 0
        volume_ratio = volume.iloc[-1] / volume.rolling(20).mean().iloc[-1] if volume.rolling(20).mean().iloc[-1] > 0 else 1

        support = close.rolling(20).min().iloc[-1]
        resistance = close.rolling(20).max().iloc[-1]

        ema_distance = (price - ema21) / ema21 * 100 if ema21 > 0 else 0
        volatilite_band = (bb_upper - bb_lower) / bb_lower * 100 if bb_lower > 0 else 0

        return {
            "price": round(price, 2),
            "rsi": round(rsi, 1),
            "macd": round(macd_line, 2),
            "macd_signal": round(macd_signal, 2),
            "macd_histogram": round(macd_hist, 2),
            "bb_pct": round(bb_pct, 3),
            "bb_width": round(volatilite_band, 2),
            "ema9": round(ema9, 2),
            "ema21": round(ema21, 2),
            "ema50": round(ema50, 2),
            "ema_distance_pct": round(ema_distance, 2),
            "atr": round(atr, 2),
            "stoch_k": round(stoch_k, 1),
            "stoch_d": round(stoch_d, 1),
            "adx": round(adx, 1),
            "cci": round(cci, 1),
            "williams_r": round(willr, 1),
            "price_change_5": round(price_change_5, 2),
            "price_change_20": round(price_change_20, 2),
            "volume_ratio": round(volume_ratio, 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
        }

    def _fallback_indicators(self, df):
        close = df['close']
        price = close.iloc[-1]
        rsi = self._calc_rsi(close, 14)
        ema9 = close.ewm(span=9).mean().iloc[-1]
        ema21 = close.ewm(span=21).mean().iloc[-1]
        price_change_5 = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100 if close.iloc[-5] > 0 else 0
        vol_ratio = df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1] if df['volume'].rolling(20).mean().iloc[-1] > 0 else 1
        return {
            "price": round(price, 2), "rsi": round(rsi, 1),
            "ema9": round(ema9, 2), "ema21": round(ema21, 2),
            "price_change_5": round(price_change_5, 2),
            "volume_ratio": round(vol_ratio, 2),
        }

    def _calc_rsi(self, close, period=14):
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]

    def _build_prompt(self, ind):
        data_json = json.dumps(ind, indent=2)
        return (
            "Sen profesyonel bir BTC trading botusun. "
            "Sana gelen teknik indikator ve piyasa verilerini analiz et ve "
            "sadece su formatta JSON cevap ver:\n\n"
            '{"action": "BUY", "reason": "kisa aciklama", "confidence": 0.0-1.0}\n'
            'veya {"action": "SELL", "reason": "...", "confidence": 0.0-1.0}\n'
            'veya {"action": "HOLD"}\n\n'
            "KARAR YONERGELERI:\n"
            "BUY: RSI < 35 (asiri satim), MACD histogram pozitife donuyor, "
            "fiyat EMA9 ustunde, Stoch K > D (dip donusu), ADX dusuk veya yukseliste, "
            "bid_ask_ratio > 1.2 (alis baskisi), Williams %R < -80.\n\n"
            "SELL: RSI > 68 (asiri alim), MACD histogram negatife donuyor, "
            "fiyat EMA9 altinda, Stoch K < D (tepe donusu), ADX > 25 ve satis yonunde, "
            "bid_ask_ratio < 0.8 (satis baskisi), Williams %R > -20.\n\n"
            "HOLD: Net sinyal yok, piyasa belirsiz. ADX < 20 ise range, "
            "bekleme yap.\n\n"
            "CONFIDENCE: 0.0 (belirsiz) ile 1.0 (cok guclu sinyal) arasi.\n"
            "0.4+ isleme alinir, 0.7+ cok guclu sinyaldir.\n\n"
            "Veri:\n" + data_json
        )

    def _call_deepseek(self, prompt):
        headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "Sen bir BTC trading botusun. Sadece JSON formatinda yanit ver."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 200
        }
        r = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
        return r.json()

    def _parse_response(self, response, indicators):
        try:
            content = response['choices'][0]['message']['content'].strip()
            if '```' in content:
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
                content = content.strip()
            result = json.loads(content)
            action = result.get('action', 'HOLD').upper()
            reason = result.get('reason', 'AI karari')
            confidence = float(result.get('confidence', 0.5))
            self.last_decision = {
                "action": action,
                "confidence": confidence,
                "reason": f"DeepSeek: {reason}",
                "indicators": indicators,
                "time": datetime.now().isoformat()
            }
            return self.last_decision
        except Exception:
            content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
            action = "SELL" if "SELL" in content else "BUY" if "BUY" in content else "HOLD"
            self.last_decision = {
                "action": action,
                "confidence": 0.5,
                "reason": "DeepSeek parse edildi",
                "indicators": indicators,
                "time": datetime.now().isoformat()
            }
            return self.last_decision

    def get_last_decision(self):
        return self.last_decision


ai = DeepSeekAI()
