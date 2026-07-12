import pandas as pd
import numpy as np
import ta


class Analyzer:
    def analyze(self, df):
        if len(df) < 50:
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]
        price = close.iloc[-1]

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        rsi_prev = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-2]

        ema8 = ta.trend.EMAIndicator(close, window=8).ema_indicator()
        ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator()
        sling_colors = ['GREEN' if e8 > e21 else 'RED' for e8, e21 in zip(ema8, ema21)]
        sling_color = sling_colors[-1]
        sling_dist = round((ema8.iloc[-1] - ema21.iloc[-1]) / ema21.iloc[-1] * 100, 2) if ema21.iloc[-1] > 0 else 0

        ema_cross = "bullish" if ema8.iloc[-1] > ema21.iloc[-1] else "bearish"

        macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = macd.macd().iloc[-1]
        signal_line = macd.macd_signal().iloc[-1]
        macd_hist = macd.macd_diff().iloc[-1]
        macd_hist_prev = macd.macd_diff().iloc[-2]
        macd_line_prev = macd.macd().iloc[-2]
        signal_line_prev = macd.macd_signal().iloc[-2]
        macd_cross_below = 1 if macd_hist_prev <= 0 and macd_hist > 0 else 0
        macd_cross_above = 1 if macd_hist_prev >= 0 and macd_hist < 0 else 0

        rsi_8 = ta.momentum.RSIIndicator(close, window=8).rsi()
        min_rsi = rsi_8.rolling(window=10).min()
        max_rsi = rsi_8.rolling(window=10).max()
        stoch_raw = ((rsi_8 - min_rsi) / (max_rsi - min_rsi)) * 100
        stoch_k = stoch_raw.rolling(window=3).mean()
        stoch_rsi_val = round(stoch_k.iloc[-1], 2)
        stoch_rsi_prev = round(stoch_k.iloc[-2], 2)

        wt_ema = ta.trend.EMAIndicator(close, window=10).ema_indicator()
        wt_esa = ta.trend.EMAIndicator(close, window=12).ema_indicator()
        wt_h = (high - wt_esa) / (wt_esa * 0.015).replace(0, np.nan)
        wt_tci = ta.trend.EMAIndicator(wt_h.fillna(0), window=5).ema_indicator()
        wt_tci2 = ta.trend.EMAIndicator(wt_tci, window=3).ema_indicator()
        wt_tci_val = round(wt_tci.iloc[-1], 2) if not pd.isna(wt_tci.iloc[-1]) else 0
        wt_tci2_val = round(wt_tci2.iloc[-1], 2) if not pd.isna(wt_tci2.iloc[-1]) else 0

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_pct = bb.bollinger_pband().iloc[-1]

        atr = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range().iloc[-1]

        vol_sma20 = volume.rolling(20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_sma20 if vol_sma20 > 0 else 1

        price_change_5 = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100 if close.iloc[-5] > 0 else 0

        support = close.rolling(20).min().iloc[-1]
        resistance = close.rolling(20).max().iloc[-1]

        recent_high_3 = high.tail(3).max()
        recent_low_3 = low.tail(3).min()
        prev_high_10 = high.tail(13).head(10).max()
        prev_low_10 = low.tail(13).head(10).min()

        breakout_up = 1.0 if price > prev_high_10 and recent_high_3 == price and vol_ratio > 1.2 else 0.0
        breakout_down = 1.0 if price < prev_low_10 and recent_low_3 == price and vol_ratio > 1.2 else 0.0

        ema_dist = (close.iloc[-1] - ema21.iloc[-1]) / ema21.iloc[-1] * 100

        # --- Ek Göstergeler (sistem kendisi deneye-yanıla öğrensin diye zengin veri) ---
        adx = ta.trend.ADXIndicator(high, low, close, window=14).adx().iloc[-1]
        di_plus = ta.trend.ADXIndicator(high, low, close, window=14).adx_pos().iloc[-1]
        di_minus = ta.trend.ADXIndicator(high, low, close, window=14).adx_neg().iloc[-1]

        cci = ta.trend.CCIIndicator(close, window=20).cci().iloc[-1]

        williams_r = ta.momentum.WilliamsRIndicator(high, low, close, lbp=14).wr().iloc[-1]

        obv = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        obv_sma = obv.rolling(20).mean().iloc[-1]
        obv_signal = 1.0 if obv.iloc[-1] > obv_sma else (-1.0 if obv.iloc[-1] < obv_sma else 0.0)

        mfi = ta.volume.MFIIndicator(high, low, close, volume, window=14).money_flow_index().iloc[-1]

        roc = ta.momentum.ROCIndicator(close, window=12).roc().iloc[-1]

        # VWAP (tipik fiyat ağırlıklı)
        tp = (high + low + close) / 3
        vwap_cum = (tp * volume).rolling(20).sum().iloc[-1]
        vol_cum = volume.rolling(20).sum().iloc[-1]
        vwap = vwap_cum / vol_cum if vol_cum > 0 else price
        vwap_dist = (price - vwap) / vwap * 100 if vwap > 0 else 0

        # Donchian kanalı (20)
        donchian_high = high.rolling(20).max().iloc[-1]
        donchian_low = low.rolling(20).min().iloc[-1]
        donchian_mid = (donchian_high + donchian_low) / 2
        donchian_pos = (price - donchian_low) / (donchian_high - donchian_low) if donchian_high > donchian_low else 0.5

        # Bileşik momentum skoru (-100..+100)
        mom_score = 0.0
        mom_score += 30 if ema_cross == "bullish" else -30
        mom_score += np.sign(macd_hist) * min(abs(macd_hist) * 200, 25)
        mom_score += (rsi - 50) * 0.4
        mom_score += (williams_r + 50) * 0.2
        mom_score = max(-100, min(100, mom_score))

        market_regime = "strong_trend" if (not pd.isna(adx) and adx > 25) else ("ranging" if (not pd.isna(adx) and adx < 20) else "undefined")

        return {
            "price": round(price, 2),
            "adx": round(adx, 1) if not pd.isna(adx) else 0,
            "di_plus": round(di_plus, 1) if not pd.isna(di_plus) else 0,
            "di_minus": round(di_minus, 1) if not pd.isna(di_minus) else 0,
            "cci": round(cci, 1) if not pd.isna(cci) else 0,
            "williams_r": round(williams_r, 1) if not pd.isna(williams_r) else -50,
            "obv_signal": obv_signal,
            "mfi": round(mfi, 1) if not pd.isna(mfi) else 50,
            "roc": round(roc, 2) if not pd.isna(roc) else 0,
            "vwap": round(vwap, 2),
            "vwap_dist": round(vwap_dist, 2),
            "donchian_high": round(donchian_high, 2),
            "donchian_low": round(donchian_low, 2),
            "donchian_pos": round(donchian_pos, 3),
            "momentum_score": round(mom_score, 1),
            "market_regime": market_regime,
            "rsi": round(rsi, 1),
            "rsi_prev": round(rsi_prev, 1),
            "ema8": round(ema8.iloc[-1], 2),
            "ema21": round(ema21.iloc[-1], 2),
            "ema_cross": ema_cross,
            "ema_dist": round(ema_dist, 2),
            "sling_color": sling_color,
            "sling_dist": sling_dist,
            "sling_colors": sling_colors,
            "macd_line": round(macd_line, 2),
            "signal_line": round(signal_line, 2),
            "macd_hist": round(macd_hist, 2),
            "macd_hist_prev": round(macd_hist_prev, 2),
            "macd_line_prev": round(macd_line_prev, 2),
            "signal_line_prev": round(signal_line_prev, 2),
            "macd_cross_below": macd_cross_below,
            "macd_cross_above": macd_cross_above,
            "stoch_rsi": stoch_rsi_val,
            "stoch_rsi_prev": stoch_rsi_prev,
            "wt_tci": wt_tci_val,
            "wt_tci2": wt_tci2_val,
            "bb_pct": round(bb_pct, 3),
            "bb_upper": round(bb_upper, 2),
            "bb_lower": round(bb_lower, 2),
            "atr": round(atr, 2),
            "atr_pct": round(atr / price * 100, 2) if price > 0 else 0,
            "vol_ratio": round(vol_ratio, 2),
            "price_change_5": round(price_change_5, 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "breakout_up": breakout_up,
            "breakout_down": breakout_down,
        }


analyzer = Analyzer()
