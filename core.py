import sys
sys.path.insert(0, '.')
import os
import time
import threading
import pandas as pd
import ta
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

ALPACA_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

SYMBOLS = ["BTC/USD", "ETH/USD"]
POSITION_SIZE = 300
STOP_LOSS = 0.008
TAKE_PROFIT = 0.012
CHECK_INTERVAL = 60

from alpaca.trading.client import TradingClient
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.requests import CryptoLatestQuoteRequest

trading = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True, url_override=ALPACA_URL)
data_client = CryptoHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)


def get_price(sym):
    r = data_client.get_crypto_latest_quote(CryptoLatestQuoteRequest(symbol_or_symbols=sym))
    return float(r[sym].ask_price)


def get_bars(sym, limit=60):
    end = datetime.utcnow()
    start = end - timedelta(hours=4)
    req = CryptoBarsRequest(symbol_or_symbols=[sym], timeframe=TimeFrame.Minute,
                            start=start, end=end, limit=limit)
    bars = data_client.get_crypto_bars(req)
    df = bars.df
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.index, pd.MultiIndex):
        df = df.droplevel(0)
    df = df.reset_index()
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"timestamp": "datetime"})
    return df[["datetime", "open", "high", "low", "close", "volume"]]


def get_account():
    acc = trading.get_account()
    return {
        "portfolio_value": float(acc.portfolio_value),
        "cash": float(acc.cash),
        "buying_power": float(acc.buying_power),
    }


def get_positions():
    positions = trading.get_all_positions()
    return [{
        "symbol": p.symbol, "qty": float(p.qty),
        "market_value": float(p.market_value),
        "unrealized_pl": float(p.unrealized_pl),
        "avg_entry_price": float(p.avg_entry_price),
    } for p in positions]


def get_position(sym):
    target = sym.replace("/", "")
    for p in get_positions():
        if p["symbol"] == target:
            return p
    return None


def cancel_all_orders():
    trading.cancel_orders()


def buy(sym, qty=None):
    price = get_price(sym)
    if qty is None:
        qty = round(POSITION_SIZE / price, 6)
    trading.submit_order(MarketOrderRequest(
        symbol=sym.replace("/", ""), qty=qty,
        side=OrderSide.BUY, time_in_force=TimeInForce.GTC))
    sl = round(price * (1 - STOP_LOSS), 2)
    tp = round(price * (1 + TAKE_PROFIT), 2)
    trading.submit_order(StopOrderRequest(
        symbol=sym.replace("/", ""), qty=qty,
        side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
        stop_price=sl))
    trading.submit_order(LimitOrderRequest(
        symbol=sym.replace("/", ""), qty=qty,
        side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
        limit_price=tp))
    return {"price": price, "qty": qty, "sl": sl, "tp": tp}


def sell(sym, qty=None):
    pos = get_position(sym)
    if not pos:
        return None
    trading.cancel_orders()
    sell_qty = qty if qty else pos["qty"]
    trading.submit_order(MarketOrderRequest(
        symbol=sym.replace("/", ""), qty=sell_qty,
        side=OrderSide.SELL, time_in_force=TimeInForce.GTC))
    return {"qty": sell_qty, "pl": pos.get("unrealized_pl", 0)}


def sell_all():
    results = []
    for p in get_positions():
        try:
            trading.cancel_orders()
            trading.submit_order(MarketOrderRequest(
                symbol=p["symbol"].replace("/", ""), qty=p["qty"],
                side=OrderSide.SELL, time_in_force=TimeInForce.GTC))
            results.append({"symbol": p["symbol"], "pl": p.get("unrealized_pl", 0)})
        except:
            pass
    return results


def analyze(df):
    if len(df) < 30:
        return None

    close = df["close"]
    rsi = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
    stoch = ta.momentum.StochRSIIndicator(close, window=14)
    sk = stoch.stochrsi_k().iloc[-1] * 100
    sd = stoch.stochrsi_d().iloc[-1] * 100

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_pct = bb.bollinger_pband().iloc[-1]

    macd = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    hist = macd.macd_diff().iloc[-1]
    hist_prev = macd.macd_diff().iloc[-2]

    ema9 = ta.trend.EMAIndicator(close, window=9).ema_indicator().iloc[-1]
    ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]

    vol = df["volume"]
    vol_sma = vol.rolling(20).mean().iloc[-1]
    vol_ratio = vol.iloc[-1] / vol_sma if vol_sma > 0 else 1

    price = close.iloc[-1]

    return {
        "rsi": rsi, "sk": sk, "sd": sd, "bb_pct": bb_pct,
        "hist": hist, "hist_prev": hist_prev,
        "ema9": ema9, "ema21": ema21,
        "vol_ratio": vol_ratio, "price": price
    }


def check_signal(ind):
    if not ind:
        return None

    buy_score = 0
    sell_score = 0
    reasons = []

    rsi = ind["rsi"]
    if rsi < 30:
        buy_score += 0.3
        reasons.append(f"RSI dusuk ({rsi:.0f})")
    elif rsi < 40:
        buy_score += 0.1
    elif rsi > 70:
        sell_score += 0.3
        reasons.append(f"RSI yuksek ({rsi:.0f})")
    elif rsi > 60:
        sell_score += 0.1

    bb = ind["bb_pct"]
    if bb < 0:
        buy_score += 0.2
        reasons.append("BB altinda")
    elif bb > 1:
        sell_score += 0.2
        reasons.append("BB ustunde")

    hist = ind["hist"]
    hist_prev = ind["hist_prev"]
    if hist > 0 and hist_prev <= 0:
        buy_score += 0.25
        reasons.append("MACD kesisim")
    elif hist < 0 and hist_prev >= 0:
        sell_score += 0.25
        reasons.append("MACD kesisim")

    ema9 = ind["ema9"]
    ema21 = ind["ema21"]
    if ema9 > ema21:
        buy_score += 0.1
    else:
        sell_score += 0.1

    sk = ind["sk"]
    sd = ind["sd"]
    if sk < 20 and sd < 20:
        buy_score += 0.1
        reasons.append("Stoch asiri satim")
    elif sk > 80 and sd > 80:
        sell_score += 0.1
        reasons.append("Stoch asiri alim")

    vol = ind["vol_ratio"]
    if vol > 2:
        buy_score += 0.05
        sell_score += 0.05
        reasons.append(f"Hacim {vol:.1f}x")

    buy_score = min(buy_score, 1.0)
    sell_score = min(sell_score, 1.0)

    if buy_score > 0.5 and buy_score > sell_score:
        return ("BUY", buy_score, "; ".join(reasons))
    elif sell_score > 0.5 and sell_score > buy_score:
        return ("SELL", sell_score, "; ".join(reasons))
    return None


class Bot:
    def __init__(self):
        self.running = False
        self.paused = False
        self.total_scans = 0
        self.signals = 0
        self.last_scan = None
        self.last_signals = {}
        self.scan_results = []

    def start(self):
        if self.running:
            return False
        self.running = True
        self.paused = False
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def stop(self):
        self.running = False
        return True

    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def _loop(self):
        while self.running:
            if not self.paused:
                self.scan_once()
            time.sleep(CHECK_INTERVAL)

    def scan_once(self):
        self.total_scans += 1
        self.last_scan = datetime.now().strftime('%H:%M:%S')
        self.scan_results = []

        for sym in SYMBOLS:
            if not self.running:
                return
            try:
                df = get_bars(sym, 60)
                if df.empty:
                    self.scan_results.append({
                        "symbol": sym, "action": "HOLD", "confidence": 0,
                        "price": 0, "rsi": 0, "volume_ratio": 0, "reason": "Veri yok"
                    })
                    continue

                ind = analyze(df)
                if not ind:
                    self.scan_results.append({
                        "symbol": sym, "action": "HOLD", "confidence": 0,
                        "price": 0, "rsi": 0, "volume_ratio": 0, "reason": "Yetersiz veri"
                    })
                    continue

                sig = check_signal(ind)
                pos = get_position(sym)
                has_pos = pos is not None

                if sig:
                    action, conf, reason = sig
                    self.signals += 1
                    self.last_signals[sym] = {
                        "action": action, "confidence": conf,
                        "price": ind["price"], "reason": reason,
                        "rsi": ind["rsi"], "time": self.last_scan
                    }
                    self.scan_results.append({
                        "symbol": sym, "action": action, "confidence": conf,
                        "price": ind["price"], "rsi": ind["rsi"],
                        "volume_ratio": ind["vol_ratio"], "reason": reason
                    })
                else:
                    self.scan_results.append({
                        "symbol": sym, "action": "HOLD", "confidence": 0,
                        "price": ind["price"], "rsi": ind["rsi"],
                        "volume_ratio": ind["vol_ratio"],
                        "reason": f"Buy:{0:.0%} Sell:{0:.0%}"
                    })

            except Exception as e:
                self.scan_results.append({
                    "symbol": sym, "action": "HOLD", "confidence": 0,
                    "price": 0, "rsi": 0, "volume_ratio": 0, "reason": str(e)[:50]
                })

    def get_status(self):
        try:
            acc = get_account()
            positions = get_positions()
            return {
                "running": self.running,
                "paused": self.paused,
                "total_scans": self.total_scans,
                "signals": self.signals,
                "last_scan": self.last_scan,
                "symbols": SYMBOLS,
                "position_size": POSITION_SIZE,
                "stop_loss": STOP_LOSS,
                "take_profit": TAKE_PROFIT,
                "balance": acc,
                "positions": positions,
                "scan_results": self.scan_results,
                "last_signals": self.last_signals,
            }
        except Exception as e:
            return {
                "running": self.running,
                "paused": self.paused,
                "total_scans": self.total_scans,
                "signals": self.signals,
                "last_scan": self.last_scan,
                "error": str(e)
            }


bot = Bot()
