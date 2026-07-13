import time
import requests
import pandas as pd
import numpy as np
from src.config import settings
from src.analyzer import analyzer


SCALP_INDICATOR_KEYS = [
    "price", "rsi", "rsi_prev", "ema8", "ema21", "ema_cross", "ema_dist",
    "macd_line", "macd_hist", "macd_hist_prev", "stoch_rsi", "bb_pct",
    "bb_upper", "bb_lower", "atr", "atr_pct", "vol_ratio", "momentum_score",
    "sling_color", "breakout_up", "breakout_down", "support", "resistance",
]

# Binance bölge engeli olabilir; bu yüzden veri katmanı çoklu kaynaktan beslenir:
#   1) Binance public REST (anahtar gerektirmez)
#   2) CoinGecko public API (anahtar gerektirmez)
#   3) Hiçbiri çalışmazsa sentetik (rastgele yürüyen) fiyat üretilir
# Böylece simülasyon HER KOŞULDA çalışır; gerçek işlem (executor) ise yalnızca
# açıkça EXECUTOR_MODE=binance + API key verilirse yapılır.

_BINANCE_REST = "https://api.binance.com/api/v3"
_COINGECKO_REST = "https://api.coingecko.com/api/v3"

_VALID_TF = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h",
             "6h", "8h", "12h", "1d", "3d", "1w", "1M"}


class Trader:
    def __init__(self):
        self.symbol = settings.symbol
        self._last_price = None
        self._last_price_ts = 0
        self._last_source = None

    # ──────────────────────────────────────────────────────────────
    #  Yardımcılar
    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def _tf_to_min(tf):
        tf = str(tf).strip().lower()
        if tf.endswith("m"):
            return int(tf[:-1] or 1)
        if tf.endswith("h"):
            return int(tf[:-1]) * 60
        if tf.endswith("d"):
            return int(tf[:-1]) * 1440
        try:
            return int(tf)
        except Exception:
            return 1

    def _coingecko_id(self):
        base = settings.base_asset.upper()
        return {
            "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
            "SOL": "solana", "XRP": "ripple", "ADA": "cardano",
        }.get(base, base.lower())

    # ──────────────────────────────────────────────────────────────
    #  Fiyat
    # ──────────────────────────────────────────────────────────────
    def get_price(self):
        # 5 sn içinde taze fiyat varsa yeniden ağ çağrısı yapma
        if self._last_price and (time.time() - self._last_price_ts) < 5:
            return self._last_price

        pair = self.symbol.replace("/", "")
        # 1) Binance
        try:
            r = requests.get(f"{_BINANCE_REST}/ticker/price?symbol={pair}", timeout=8)
            if r.status_code == 200:
                p = float(r.json()["price"])
                self._last_price, self._last_source, self._last_price_ts = p, "binance", time.time()
                return p
        except Exception:
            pass

        # 2) CoinGecko
        try:
            cid = self._coingecko_id()
            r = requests.get(f"{_COINGECKO_REST}/simple/price?ids={cid}&vs_currencies=usd", timeout=10)
            if r.status_code == 200:
                p = float(r.json()[cid]["usd"])
                self._last_price, self._last_source, self._last_price_ts = p, "coingecko", time.time()
                return p
        except Exception:
            pass

        # 3) Son bilinen fiyat
        if self._last_price:
            return self._last_price

        self._last_price = 60000.0
        self._last_price_ts = time.time()
        return self._last_price

    # ──────────────────────────────────────────────────────────────
    #  OHLCV (mum) verisi
    # ──────────────────────────────────────────────────────────────
    def _binance_klines(self, interval, limit):
        pair = self.symbol.replace("/", "")
        try:
            r = requests.get(
                f"{_BINANCE_REST}/klines?symbol={pair}&interval={interval}&limit={limit}",
                timeout=10,
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if not isinstance(data, list) or not data:
                return None
            rows = [[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in data]
            df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df[["datetime", "open", "high", "low", "close", "volume"]]
            self._last_price = float(df["close"].iloc[-1])
            self._last_source = "binance"
            return df
        except Exception as e:
            print(f"[TRADER] Binance veri hatasi: {e}")
            return None

    def _coingecko_bars(self, interval, limit):
        minutes = self._tf_to_min(interval)
        total_min = minutes * limit
        days = max(1, int(total_min / 1440) + 1)
        if days > 90:
            days = 90
        try:
            cid = self._coingecko_id()
            r = requests.get(
                f"{_COINGECKO_REST}/coins/{cid}/market_chart?vs_currency=usd&days={days}",
                timeout=15,
            )
            if r.status_code != 200:
                return None
            prices = r.json().get("prices")
            if not prices:
                return None
            ts = [p[0] for p in prices]
            px = [p[1] for p in prices]
            df = pd.DataFrame({"timestamp": ts, "close": px})
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.set_index("datetime")
            spacing = (df.index[1] - df.index[0]).total_seconds() / 60 if len(df) > 1 else minutes
            eff = max(minutes, int(round(spacing)))
            rule = f"{eff}min"
            o = df["close"].resample(rule).first()
            h = df["close"].resample(rule).max()
            l = df["close"].resample(rule).min()
            c = df["close"].resample(rule).last()
            v = df["close"].resample(rule).count() * 0.0
            out = pd.DataFrame({
                "datetime": o.index, "open": o.values, "high": h.values,
                "low": l.values, "close": c.values, "volume": v.values,
            }).dropna().reset_index(drop=True)
            if len(out) > limit:
                out = out.tail(limit)
            if len(out) < 2:
                return None
            self._last_price = float(out["close"].iloc[-1])
            self._last_source = "coingecko"
            return out[["datetime", "open", "high", "low", "close", "volume"]]
        except Exception as e:
            print(f"[TRADER] CoinGecko veri hatasi: {e}")
            return None

    def _fetch_ohlcv(self, interval, limit):
        df = self._binance_klines(interval, limit)
        if df is not None and len(df) >= 2:
            return df
        df = self._coingecko_bars(interval, limit)
        if df is not None and len(df) >= 2:
            return df
        return None

    def get_bars(self, limit=100, timeframe="1m"):
        tf = str(timeframe).strip().lower()
        if tf in _VALID_TF:
            df = self._fetch_ohlcv(tf, limit)
        else:
            try:
                base = self._fetch_ohlcv("1m", max(limit * 6, 600))
            except Exception:
                base = None
            df = self._resample(base, tf) if base is not None and len(base) >= 2 else None

        if df is None or len(df) < 2:
            print("[TRADER] Tum veri kaynaklari basarisiz -> sentetik veri uretiliyor.")
            df = self._synthetic_bars(tf, limit)
        return df

    # ──────────────────────────────────────────────────────────────
    #  Sentetik (son çare) veri — simülasyon asla kırılmasın diye
    # ──────────────────────────────────────────────────────────────
    def _synthetic_bars(self, timeframe, limit, anchor=None):
        minutes = self._tf_to_min(timeframe)
        now = pd.Timestamp.now().floor(f"{minutes}min")
        idx = pd.date_range(end=now, periods=limit, freq=f"{minutes}min")
        price = anchor if anchor and anchor > 0 else (self._last_price or 60000.0)
        np.random.seed((int(time.time()) % 100000) + limit)
        rets = np.random.normal(0, 0.0015, size=limit)
        closes = np.maximum(price * np.cumprod(1 + rets), 1.0)
        df = pd.DataFrame({"datetime": idx, "close": closes})
        df["open"] = df["close"].shift(1).fillna(df["close"].iloc[0])
        noise = df["close"] * 0.0008
        df["high"] = df[["open", "close"]].max(axis=1) + noise
        df["low"] = df[["open", "close"]].min(axis=1) - noise
        df["volume"] = np.random.uniform(10, 100, size=limit)
        self._last_source = "synthetic"
        return df[["datetime", "open", "high", "low", "close", "volume"]]

    # ──────────────────────────────────────────────────────────────
    #  Orderbook / son işlemler (Binance yoksa nötr sentetik)
    # ──────────────────────────────────────────────────────────────
    def get_orderbook(self, limit=50):
        pair = self.symbol.replace("/", "")
        try:
            r = requests.get(f"{_BINANCE_REST}/depth?symbol={pair}&limit=50", timeout=8)
            if r.status_code == 200:
                book = r.json()
                bids, asks = book["bids"], book["asks"]
                bid_vol = sum(float(b[1]) for b in bids)
                ask_vol = sum(float(a[1]) for a in asks)
                top10_bid = sum(float(b[1]) for b in bids[:10])
                top10_ask = sum(float(a[1]) for a in asks[:10])
                imbalance = round(bid_vol / ask_vol, 2) if ask_vol > 0 else 1.0
                return {
                    "bid_ask_ratio": imbalance,
                    "bid_ask_sinyal": "alis_baskisi" if imbalance > 1.2 else "satis_baskisi" if imbalance < 0.8 else "notr",
                    "spread": round(float(asks[0][0]) - float(bids[0][0]), 2),
                    "bid_volume": round(bid_vol, 4),
                    "ask_volume": round(ask_vol, 4),
                    "top10_bid": round(top10_bid, 4),
                    "top10_ask": round(top10_ask, 4),
                }
        except Exception:
            pass
        return {
            "bid_ask_ratio": 1.0, "bid_ask_sinyal": "notr", "spread": 0.0,
            "bid_volume": 0.0, "ask_volume": 0.0, "top10_bid": 0.0, "top10_ask": 0.0,
        }

    def get_recent_trades(self, limit=50):
        pair = self.symbol.replace("/", "")
        try:
            r = requests.get(f"{_BINANCE_REST}/trades?symbol={pair}&limit={limit}", timeout=8)
            if r.status_code == 200:
                trades = r.json()
                buys = sum(1 for t in trades if t.get("isBuyerMaker") is False)
                return {"buy_sell_ratio": round(buys / max(len(trades) - buys, 1), 2)}
        except Exception:
            pass
        return {"buy_sell_ratio": 1.0}

    # ──────────────────────────────────────────────────────────────
    #  Scalping (M10/M30) çoklu periyot
    # ──────────────────────────────────────────────────────────────
    def get_scalp_indicators(self, limit=100):
        result = {}
        for tf in settings.scalp_timeframes:
            tf = tf.strip()
            if not tf:
                continue
            try:
                df = self.get_bars(limit=limit, timeframe=tf)
                if df is not None and len(df) >= 50:
                    t = analyzer.analyze(df)
                    if t:
                        result[tf] = t
                        print(f"[TRADER] {tf} scalp indikatorleri yuklendi (RSI={t.get('rsi')}, EMA={t.get('ema_cross')})")
            except Exception as e:
                print(f"[TRADER] {tf} scalp veri hatasi: {e}")
        return result

    @staticmethod
    def _resample(df_1m, timeframe):
        """1m mumlarini <n>m (orn. 10m) periyoduna pandas ile yeniden ornekle."""
        minutes = int(timeframe[:-1])
        rule = f"{minutes}min"
        d = df_1m.copy()
        if "datetime" not in d.columns and "timestamp" in d.columns:
            d["datetime"] = pd.to_datetime(d["timestamp"], unit="ms")
        d = d.set_index("datetime")
        o = d["open"].resample(rule).first()
        h = d["high"].resample(rule).max()
        l = d["low"].resample(rule).min()
        c = d["close"].resample(rule).last()
        v = d["volume"].resample(rule).sum()
        out = pd.DataFrame({
            "datetime": o.index,
            "open": o.values, "high": h.values, "low": l.values,
            "close": c.values, "volume": v.values,
        }).dropna().reset_index(drop=True)
        return out

    def merge_scalp_indicators(self, teknik, scalp):
        if not teknik or not scalp:
            return teknik
        for tf, t in scalp.items():
            prefix = tf.replace(":", "").replace("/", "")
            for k in SCALP_INDICATOR_KEYS:
                if k in t:
                    teknik[f"{prefix}_{k}"] = t[k]
        return teknik


trader = Trader()
