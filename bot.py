import sys
sys.path.insert(0, '.')
import os
import time
import threading
import requests
import pandas as pd
import ta
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

ALPACA_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

POSITION_SIZE = 300
STOP_LOSS = 0.008
TAKE_PROFIT = 0.012
CHECK_INTERVAL = 60

SYMBOLS = ["BTC/USD", "ETH/USD"]

from alpaca.trading.client import TradingClient
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.requests import CryptoLatestQuoteRequest

trading = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True, url_override=ALPACA_URL)
data = CryptoHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)


class Telegram:
    def __init__(self):
        self.base = f"https://api.telegram.org/bot{TG_TOKEN}"
        self.last_id = 0
        self.pending = {}
        self.pending_sell = {}
        self.counter = 0
        self._sent = set()
        self._lock = threading.Lock()

    def send(self, text, silent=False):
        try:
            payload = {"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}
            if silent:
                payload["disable_notification"] = True
            requests.post(f"{self.base}/sendMessage", json=payload, timeout=10)
        except:
            pass

    def get_updates(self):
        try:
            r = requests.get(f"{self.base}/getUpdates",
                             params={"offset": self.last_id + 1, "timeout": 3}, timeout=10)
            return r.json().get("result", []) if r.status_code == 200 else []
        except:
            return []

    def handle(self, text, chat_id):
        if str(chat_id) != str(TG_CHAT):
            return

        low = text.strip().lower()

        if low in ["yap", "evet", "1"]:
            self._approve("buy")
            return
        if low in ["yapma", "hayir", "0"]:
            self._reject("buy")
            return
        if low in ["satis", "satacak"]:
            self._approve("sell")
            return
        if low in ["sakla", "tut"]:
            self._reject("sell")
            return

        if low.startswith("yap ") and low.split()[-1].isdigit():
            self._approve("buy", int(low.split()[-1]))
            return
        if low.startswith("satis ") and low.split()[-1].isdigit():
            self._approve("sell", int(low.split()[-1]))
            return

        if low in ["sellall", "sell all", "hepsini sat"]:
            self._sell_all()
            return

        parts = low.split()
        if len(parts) == 2 and parts[0] in ["/sell", "sell"]:
            self._sell_one(parts[1].upper())
            return

        if low in ["/start", "start"]:
            self._cmd_start()
        elif low in ["/stop", "stop"]:
            self._cmd_stop()
        elif low in ["/status", "status", "/durum"]:
            self._cmd_status()
        elif low in ["/pos", "pozisyon", "/positions"]:
            self._cmd_positions()
        elif low in ["/balance", "bakiye", "/b"]:
            self._cmd_balance()
        elif low in ["/scan", "scan"]:
            self._cmd_scan()
        elif low in ["/help", "/yardim"]:
            self._cmd_help()

    def _approve(self, kind, id=None):
        with self._lock:
            store = self.pending if kind == "buy" else self.pending_sell
            if not store:
                self.send("Bekleyen islem yok.")
                return
            if id and id in store:
                trade = store.pop(id)
                if kind == "buy":
                    self._exec_buy(trade)
                else:
                    self._exec_sell(trade)
                return
            if store:
                key = max(store.keys())
                trade = store.pop(key)
                if kind == "buy":
                    self._exec_buy(trade)
                else:
                    self._exec_sell(trade)

    def _reject(self, kind):
        with self._lock:
            store = self.pending if kind == "buy" else self.pending_sell
            if store:
                key = max(store.keys())
                trade = store.pop(key)
                self.send(f"<b>{trade['symbol']}</b> iptal edildi.")
            else:
                self.send("Bekleyen islem yok.")

    def _exec_buy(self, trade):
        sym = trade["symbol"]
        self.send(f"<b>{sym}</b> alis basliyor...")
        try:
            price = get_price(sym)
            qty = round(POSITION_SIZE / price, 6)
            trading.submit_order(MarketOrderRequest(
                symbol=sym.replace("/", ""), qty=qty,
                side=OrderSide.BUY, time_in_force=TimeInForce.GTC))

            sl = price * (1 - STOP_LOSS)
            tp = price * (1 + TAKE_PROFIT)
            trading.submit_order(StopOrderRequest(
                symbol=sym.replace("/", ""), qty=qty,
                side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
                stop_price=round(sl, 2)))
            trading.submit_order(LimitOrderRequest(
                symbol=sym.replace("/", ""), qty=qty,
                side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
                limit_price=round(tp, 2)))

            self.send(
                f"<b>ALIS TAMAM</b>  <code>{sym}</code>\n"
                f"Miktar: <code>{qty:.6f}</code>\n"
                f"Giris: <code>${price:,.2f}</code>\n"
                f"SL: <code>${sl:,.2f}</code>  TP: <code>${tp:,.2f}</code>\n"
                f"Kar hedef: %{TAKE_PROFIT*100:.1f}")
        except Exception as e:
            self.send(f"<b>{sym}</b> hata:\n<code>{str(e)[:200]}</code>")

    def _exec_sell(self, trade):
        sym = trade["symbol"]
        self.send(f"<b>{sym}</b> satis basliyor...")
        try:
            pos = get_position(sym)
            if not pos:
                self.send(f"<b>{sym}</b> pozisyon yok.")
                return
            qty = pos["qty"]
            trading.cancel_orders()
            trading.submit_order(MarketOrderRequest(
                symbol=sym.replace("/", ""), qty=qty,
                side=OrderSide.SELL, time_in_force=TimeInForce.GTC))
            pl = pos.get("unrealized_pl", 0)
            self.send(
                f"<b>SATIS TAMAM</b>  <code>{sym}</code>\n"
                f"Miktar: <code>{qty:.6f}</code>\n"
                f"K/Z: <code>${pl:+,.4f}</code>")
        except Exception as e:
            self.send(f"<b>{sym}</b> hata:\n<code>{str(e)[:200]}</code>")

    def _sell_all(self):
        positions = get_positions()
        if not positions:
            self.send("Pozisyon yok.")
            return
        self.send(f"<b>HEPSINI SAT</b> ({len(positions)} coin)")
        for p in positions:
            try:
                trading.cancel_orders()
                trading.submit_order(MarketOrderRequest(
                    symbol=p["symbol"].replace("/", ""), qty=p["qty"],
                    side=OrderSide.SELL, time_in_force=TimeInForce.GTC))
                self.send(f"<b>{p['symbol']}</b> satildi  K/Z: ${p.get('unrealized_pl',0):+,.4f}")
            except Exception as e:
                self.send(f"<b>{p['symbol']}</b> hata: {str(e)[:100]}")

    def _sell_one(self, coin):
        if not coin.endswith("/USD"):
            coin = coin + "/USD"
        pos = get_position(coin)
        if not pos:
            self.send(f"<code>{coin}</code> pozisyon yok.")
            return
        try:
            trading.cancel_orders()
            trading.submit_order(MarketOrderRequest(
                symbol=coin.replace("/", ""), qty=pos["qty"],
                side=OrderSide.SELL, time_in_force=TimeInForce.GTC))
            self.send(f"<b>{coin}</b> satildi  K/Z: ${pos.get('unrealized_pl',0):+,.4f}")
        except Exception as e:
            self.send(f"<b>{coin}</b> hata: {str(e)[:100]}")

    def _cmd_start(self):
        if bot.running:
            self.send("Bot zaten calisiyor!")
            return
        bot.start()
        self.send(
            f"<b>BOT BASLATILDI</b>\n\n"
            f"Coin: BTC, ETH\n"
            f"Islem: ${POSITION_SIZE}\n"
            f"SL: %{STOP_LOSS*100:.1f}  TP: %{TAKE_PROFIT*100:.1f}\n"
            f"Hedef: Surekli %1 kar\n\n"
            f"/status - durum\n/pos - pozisyonlar\n/help - komutlar")

    def _cmd_stop(self):
        if not bot.running:
            self.send("Bot zaten durdu!")
            return
        bot.stop()
        self.send("<b>BOT DURDURULDU</b>")

    def _cmd_status(self):
        if not bot.running:
            self.send("Bot calismiyor. /start ile baslatin.")
            return
        msg = (
            f"<b>DURUM</b>\n\n"
            f"Durum: <b>{'DURAKLATILDI' if bot.paused else 'AKTIF'}</b>\n"
            f"Tarama: {bot.total_scans}\n"
            f"Sinyal: {bot.signals}\n"
            f"Coin: BTC, ETH\n"
            f"Son: {bot.last_scan or '-'}")
        if self.pending:
            msg += f"\nBekleyen alis: {len(self.pending)}"
        if self.pending_sell:
            msg += f"\nBekleyen satis: {len(self.pending_sell)}"
        self.send(msg)

    def _cmd_positions(self):
        positions = get_positions()
        if not positions:
            self.send("Pozisyon yok.")
            return
        msg = "<b>POZISYONLAR</b>\n\n"
        toplam = 0
        for p in positions:
            pl = p["unrealized_pl"]
            toplam += pl
            entry = p["avg_entry_price"]
            yuzde = ((p["market_value"] - entry * p["qty"]) / (entry * p["qty"]) * 100) if entry > 0 else 0
            msg += (
                f"<code>{p['symbol']}</code>\n"
                f"  {p['qty']:.6f} @ ${entry:,.2f}\n"
                f"  Deger: ${p['market_value']:,.2f}\n"
                f"  K/Z: ${pl:+,.4f} ({yuzde:+.1f}%)\n\n")
        msg += f"Toplam: <b>${toplam:+,.4f}</b>\n\n"
        msg += "Sat: <code>sell BTC</code>  Hep: <code>sellall</code>"
        self.send(msg)

    def _cmd_balance(self):
        try:
            acc = trading.get_account()
            positions = get_positions()
            toplam_kz = sum(p.get("unrealized_pl", 0) for p in positions)
            toplam_deger = sum(p.get("market_value", 0) for p in positions)
            self.send(
                f"<b>BAKIYE</b>\n\n"
                f"Portfoy: <code>${float(acc.portfolio_value):,.2f}</code>\n"
                f"Nakit: <code>${float(acc.cash):,.2f}</code>\n"
                f"Pozisyon: <code>${toplam_deger:,.2f}</code>\n"
                f"K/Z: <code>${toplam_kz:+,.4f}</code>")
        except Exception as e:
            self.send(f"Hata: {str(e)[:100]}")

    def _cmd_scan(self):
        if not bot.running:
            self.send("Once /start lazim.")
            return
        self.send("Tarama basliyor...")
        threading.Thread(target=bot.scan_once, daemon=True).start()

    def _cmd_help(self):
        self.send(
            "<b>KOMUTLAR</b>\n\n"
            "<code>/start</code>  Baslat\n"
            "<code>/stop</code>   Durdur\n"
            "<code>/status</code> Durum\n"
            "<code>/pos</code>    Pozisyonlar\n"
            "<code>/balance</code> Bakiye\n"
            "<code>/scan</code>   Hemen tara\n\n"
            "<b>ALIS ONAY</b>\n"
            "<code>yap</code> / <code>yapma</code>\n\n"
            "<b>SATIS</b>\n"
            "<code>satis</code> / <code>sakla</code>\n"
            "<code>sell BTC</code> / <code>sellall</code>")

    def poll(self):
        print("[TG] Telegram dinleniyor...")
        while True:
            try:
                for u in self.get_updates():
                    self.last_id = u["update_id"]
                    msg = u.get("message", {})
                    txt = msg.get("text", "")
                    cid = msg.get("chat", {}).get("id", "")
                    if txt:
                        print(f"[TG] {txt}")
                        self.handle(txt, cid)
            except Exception as e:
                print(f"[TG] Hata: {e}")
            time.sleep(2)

    def start_polling(self):
        threading.Thread(target=self.poll, daemon=True).start()


def get_price(sym):
    r = data.get_crypto_latest_quote(CryptoLatestQuoteRequest(symbol_or_symbols=sym))
    return float(r[sym].ask_price)


def get_bars(sym, limit=60):
    end = datetime.utcnow()
    start = end - timedelta(hours=4)
    req = CryptoBarsRequest(symbol_or_symbols=[sym], timeframe=TimeFrame.Minute,
                            start=start, end=end, limit=limit)
    bars = data.get_crypto_bars(req)
    df = bars.df
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.index, pd.MultiIndex):
        df = df.droplevel(0)
    df = df.reset_index()
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"timestamp": "datetime"})
    return df[["datetime", "open", "high", "low", "close", "volume"]]


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


def analyze(df):
    if len(df) < 30:
        return None, None, None

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
    price_chg = (price - close.iloc[-2]) / close.iloc[-2]

    return {
        "rsi": rsi, "sk": sk, "sd": sd, "bb_pct": bb_pct,
        "hist": hist, "hist_prev": hist_prev,
        "ema9": ema9, "ema21": ema21,
        "vol_ratio": vol_ratio, "price": price, "price_chg": price_chg
    }


def check_signal(sym, indicators):
    if not indicators:
        return None

    buy_score = 0
    sell_score = 0
    reasons = []

    rsi = indicators["rsi"]
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

    bb = indicators["bb_pct"]
    if bb < 0:
        buy_score += 0.2
        reasons.append("BB altinda")
    elif bb > 1:
        sell_score += 0.2
        reasons.append("BB ustunde")

    hist = indicators["hist"]
    hist_prev = indicators["hist_prev"]
    if hist > 0 and hist_prev <= 0:
        buy_score += 0.25
        reasons.append("MACD kesisim")
    elif hist < 0 and hist_prev >= 0:
        sell_score += 0.25
        reasons.append("MACD kesisim")

    ema9 = indicators["ema9"]
    ema21 = indicators["ema21"]
    if ema9 > ema21:
        buy_score += 0.1
    else:
        sell_score += 0.1

    sk = indicators["sk"]
    sd = indicators["sd"]
    if sk < 20 and sd < 20:
        buy_score += 0.1
        reasons.append("Stoch asiri satim")
    elif sk > 80 and sd > 80:
        sell_score += 0.1
        reasons.append("Stoch asiri alim")

    vol = indicators["vol_ratio"]
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

    def start(self):
        if self.running:
            return
        self.running = True
        self.paused = False
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            if not self.paused:
                self.scan_once()
            time.sleep(CHECK_INTERVAL)

    def scan_once(self):
        self.total_scans += 1
        self.last_scan = datetime.now().strftime('%H:%M:%S')
        print(f"\n{'='*40}")
        print(f"Tarama #{self.total_scans} | {self.last_scan}")

        for sym in SYMBOLS:
            if not self.running:
                return
            try:
                df = get_bars(sym, 60)
                if df.empty:
                    continue
                ind = analyze(df)
                sig = check_signal(sym, ind)
                if sig:
                    action, conf, reason = sig
                    tag = "ALIS" if action == "BUY" else "SATIS"
                    print(f"  [{tag}] {sym} ${ind['price']:,.2f} Guven:{conf:.0%}")

                    pos = get_position(sym)
                    has_position = pos is not None

                    with tg._lock:
                        sig_key = f"{action}_{sym}_{self.total_scans}"
                        if sig_key in tg._sent:
                            continue
                        tg._sent.add(sig_key)
                        if len(tg._sent) > 100:
                            tg._sent.clear()

                    if action == "BUY" and not has_position:
                        self.signals += 1
                        tg.counter += 1
                        tid = tg.counter
                        tg.pending[tid] = {
                            "id": tid, "symbol": sym, "price": ind["price"],
                            "confidence": conf, "reason": reason
                        }
                        tg.send(
                            f"<b>ALIS ONAY</b>  <code>{sym}</code>\n\n"
                            f"Fiyat: <code>${ind['price']:,.2f}</code>\n"
                            f"Guven: <b>{conf:.0%}</b>\n"
                            f"RSI: {ind['rsi']:.1f}\n\n"
                            f"<i>{reason}</i>\n\n"
                            f"<code>yap</code> - al  |  <code>yapma</code> - alma")

                    elif action == "SELL" and has_position:
                        self.signals += 1
                        pl = pos.get("unrealized_pl", 0)
                        entry = pos.get("avg_entry_price", 0)
                        yuzde = ((ind["price"] - entry) / entry * 100) if entry > 0 else 0
                        tg.counter += 1
                        sid = tg.counter
                        tg.pending_sell[sid] = {
                            "id": sid, "symbol": sym, "price": ind["price"],
                            "confidence": conf, "reason": reason,
                            "unrealized_pl": pl
                        }
                        tg.send(
                            f"<b>SATIS ONAY</b>  <code>{sym}</code>\n\n"
                            f"Giris: <code>${entry:,.2f}</code>  Simdi: <code>${ind['price']:,.2f}</code>\n"
                            f"Degisim: <b>{yuzde:+.2f}%</b>\n"
                            f"K/Z: <b>${pl:+,.4f}</b>\n\n"
                            f"RSI: {ind['rsi']:.1f}\n"
                            f"<i>{reason}</i>\n\n"
                            f"<code>satis</code> - sat  |  <code>sakla</code> - tut")

            except Exception as e:
                print(f"  [HATA] {sym}: {e}")

        print(f"Tamamlandi | Sinyal: {self.signals}")


bot = Bot()
tg = Telegram()

if __name__ == "__main__":
    print("=" * 40)
    print("BTC/ETH BOT - Bagimsiz Telegram Botu")
    print("=" * 40)
    print(f"Coin: {', '.join(SYMBOLS)}")
    print(f"Islem: ${POSITION_SIZE}")
    print(f"SL: %{STOP_LOSS*100:.1f}  TP: %{TAKE_PROFIT*100:.1f}")
    print()

    tg.start_polling()
    tg.send(
        f"<b>SISTEM HAZIR</b>\n\n"
        f"BTC/ETH Bot - Bagimsiz calisiyor\n"
        f"Islem: ${POSITION_SIZE}  TP: %{TAKE_PROFIT*100:.1f}\n\n"
        f"Basla: <code>/start</code>")

    print("[INFO] Telegram dinleniyor... Botu /start ile baslatin")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.stop()
        print("\n[INFO] Kapatildi")
