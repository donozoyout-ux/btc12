import sys
sys.path.insert(0, '.')
import os
import time
import threading
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

from core import bot, SYMBOLS, POSITION_SIZE, STOP_LOSS, TAKE_PROFIT
from core import get_price, get_positions, get_position, buy, sell, sell_all


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
        elif low in ["/pause", "pause"]:
            self._cmd_pause()
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
            result = buy(sym)
            self.send(
                f"<b>ALIS TAMAM</b>  <code>{sym}</code>\n"
                f"Miktar: <code>{result['qty']:.6f}</code>\n"
                f"Giris: <code>${result['price']:,.2f}</code>\n"
                f"SL: <code>${result['sl']:,.2f}</code>  TP: <code>${result['tp']:,.2f}</code>\n"
                f"Kar hedef: %{TAKE_PROFIT*100:.1f}")
        except Exception as e:
            self.send(f"<b>{sym}</b> hata:\n<code>{str(e)[:200]}</code>")

    def _exec_sell(self, trade):
        sym = trade["symbol"]
        self.send(f"<b>{sym}</b> satis basliyor...")
        try:
            result = sell(sym)
            if result:
                self.send(
                    f"<b>SATIS TAMAM</b>  <code>{sym}</code>\n"
                    f"Miktar: <code>{result['qty']:.6f}</code>\n"
                    f"K/Z: <code>${result['pl']:+,.4f}</code>")
            else:
                self.send(f"<b>{sym}</b> pozisyon bulunamadi.")
        except Exception as e:
            self.send(f"<b>{sym}</b> hata:\n<code>{str(e)[:200]}</code>")

    def _sell_all(self):
        positions = get_positions()
        if not positions:
            self.send("Pozisyon yok.")
            return
        self.send(f"<b>HEPSINI SAT</b> ({len(positions)} coin)")
        results = sell_all()
        for r in results:
            self.send(f"<b>{r['symbol']}</b> satildi  K/Z: ${r['pl']:+,.4f}")

    def _sell_one(self, coin):
        if not coin.endswith("/USD"):
            coin = coin + "/USD"
        pos = get_position(coin)
        if not pos:
            self.send(f"<code>{coin}</code> pozisyon yok.")
            return
        try:
            result = sell(coin)
            if result:
                self.send(f"<b>{coin}</b> satildi  K/Z: ${result['pl']:+,.4f}")
        except Exception as e:
            self.send(f"<b>{coin}</b> hata: {str(e)[:100]}")

    def _cmd_start(self):
        if bot.running:
            self.send("Bot zaten calisiyor!")
            return
        bot.start()
        self.send(
            f"<b>BOT BASLATILDI</b>\n\n"
            f"Coin: {', '.join(SYMBOLS)}\n"
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

    def _cmd_pause(self):
        state = bot.toggle_pause()
        self.send(f"<b>{'DURAKLATILDI' if state else 'DEVAM'}</b>")

    def _cmd_status(self):
        if not bot.running:
            self.send("Bot calismiyor. /start ile baslatin.")
            return
        msg = (
            f"<b>DURUM</b>\n\n"
            f"Durum: <b>{'DURAKLATILDI' if bot.paused else 'AKTIF'}</b>\n"
            f"Tarama: {bot.total_scans}\n"
            f"Sinyal: {bot.signals}\n"
            f"Coin: {', '.join(SYMBOLS)}\n"
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
            acc = get_account()
            positions = get_positions()
            toplam_kz = sum(p.get("unrealized_pl", 0) for p in positions)
            toplam_deger = sum(p.get("market_value", 0) for p in positions)
            self.send(
                f"<b>BAKIYE</b>\n\n"
                f"Portfoy: <code>${acc['portfolio_value']:,.2f}</code>\n"
                f"Nakit: <code>${acc['cash']:,.2f}</code>\n"
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
            "<code>/pause</code>  Duraklat\n"
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


tg = Telegram()


def init_telegram():
    tg.start_polling()
    tg.send(
        f"<b>SISTEM HAZIR</b>\n\n"
        f"{', '.join(SYMBOLS)} Bot\n"
        f"Islem: ${POSITION_SIZE}  TP: %{TAKE_PROFIT*100:.1f}\n\n"
        f"Basla: <code>/start</code>")
    return tg


if __name__ == "__main__":
    print("=" * 40)
    print("BTC/ETH BOT - Telegram Botu")
    print("=" * 40)

    init_telegram()

    print("[INFO] Telegram dinleniyor... /start ile baslatin")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot.stop()
        print("\n[INFO] Kapatildi")
