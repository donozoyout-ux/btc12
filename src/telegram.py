import requests
import time
import threading
from datetime import datetime
from src.config import settings


class TelegramBot:
    def __init__(self):
        self.base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self.chat_id = settings.telegram_chat_id
        self.last_update_id = 0
        self.running = False
        self.pending = {}
        self.pending_sell = {}
        self.counter = 0
        self._lock = threading.Lock()
        self._handlers = {}
        self._on_start = None
        self._on_stop = None
        self._on_scan = None
        self._on_buy = None
        self._on_sell = None

    def send(self, text, silent=False):
        try:
            payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            if silent:
                payload["disable_notification"] = True
            requests.post(f"{self.base}/sendMessage", json=payload, timeout=10)
        except:
            pass

    def get_updates(self):
        try:
            r = requests.get(f"{self.base}/getUpdates",
                             params={"offset": self.last_update_id + 1, "timeout": 3}, timeout=10)
            return r.json().get("result", []) if r.status_code == 200 else []
        except:
            return []

    def handle(self, text, chat_id):
        if str(chat_id) != str(self.chat_id):
            return

        low = text.strip().lower().lstrip("/")

        if low in ["yap", "evet", "1", "onay"]:
            self._approve("buy")
            return
        if low in ["yapma", "hayir", "0", "iptal"]:
            self._reject("buy")
            return
        if low in ["satis", "satacak", "sat"]:
            self._approve("sell")
            return
        if low in ["sakla", "tut"]:
            self._reject("sell")
            return

        parts = low.split()
        if len(parts) == 2 and parts[0] == "yap" and parts[1].isdigit():
            self._approve("buy", int(parts[1]))
            return
        if len(parts) == 2 and parts[0] == "satis" and parts[1].isdigit():
            self._approve("sell", int(parts[1]))
            return
        if len(parts) == 2 and parts[0] in ["sell", "sellt"] and parts[1].isdigit():
            self._approve("sell", int(parts[1]))
            return

        if low in ["sellall", "sell all", "hepsini sat"]:
            self._sell_all()
            return

        if len(parts) == 2 and parts[0] in ["/sell", "sell"]:
            self._sell_one(parts[1].upper())
            return

        if low.startswith("/"):
            self._route(low)

    def _route(self, cmd):
        base = cmd.split()[0] if cmd else ""
        arg = cmd.split()[1] if len(cmd.split()) > 1 else ""

        if base in ["/start", "start"]:
            self._cmd_start()
        elif base in ["/stop", "stop"]:
            self._cmd_stop()
        elif base in ["/status", "status", "/durum"]:
            self._cmd_status()
        elif base in ["/pos", "pozisyon", "/positions"]:
            self._cmd_positions()
        elif base in ["/balance", "bakiye", "/b"]:
            self._cmd_balance()
        elif base in ["/scan", "scan"]:
            self._cmd_scan()
        elif base in ["/signals", "signals", "/sinyaller"]:
            self._cmd_signals()
        elif base in ["/memory", "memory", "/ai"]:
            self._cmd_memory()
        elif base in ["/onaylar", "onaylar"]:
            self._cmd_pending()
        elif base in ["/satislar", "satislar"]:
            self._cmd_pending_sells()
        elif base in ["/sellall", "sellall"]:
            self._sell_all()
        elif base in ["/sell", "sell"] and arg:
            self._sell_one(arg.upper())
        elif base in ["/artir", "artir"]:
            self._cmd_artir(arg)
        elif base in ["/azalt", "azalt"]:
            self._cmd_azalt(arg)
        elif base in ["/ miktar", "miktar"]:
            self._cmd_miktar()
        elif base in ["/help", "/yardim"]:
            self._cmd_help()
        else:
            self.send("Bilinmeyen komut. /help")

    def _approve(self, kind, tid=None):
        with self._lock:
            store = self.pending if kind == "buy" else self.pending_sell
            self.send(f"<b>DEBUG</b> _approve: kind={kind}, tid={tid}, bekleyen={len(store)}")
            if not store:
                self.send("Bekleyen islem yok.")
                return
            if tid and tid in store:
                trade = store.pop(tid)
                self.send(f"<b>DEBUG</b> Islem bulundu: #{tid} {trade['symbol']}")
                if kind == "buy":
                    self._exec_buy(trade)
                else:
                    self._exec_sell(trade)
                return
            if store:
                key = max(store.keys())
                trade = store.pop(key)
                self.send(f"<b>DEBUG</b> Son islem: #{key} {trade['symbol']}")
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
        from src.trader import trader
        sym = trade["symbol"]
        self.send(f"<b>DEBUG</b> _exec_buy basliyor: {sym}")
        try:
            result = trader.buy(sym)
            self.send(f"<b>DEBUG</b> Alis basarili!")
            self.send(
                f"<b>ALIS TAMAM</b>  <code>{sym}</code>\n"
                f"Miktar: <code>{result['qty']:.6f}</code>\n"
                f"Giris: <code>${result['price']:,.2f}</code>\n"
                f"SL: <code>${result['sl']:,.2f}</code>  TP: <code>${result['tp']:,.2f}</code>")
        except Exception as e:
            self.send(f"<b>DEBUG</b> Alis hatasi: {str(e)[:100]}")
            self.send(f"<b>{sym}</b> hata:\n<code>{str(e)[:200]}</code>")

    def _exec_sell(self, trade):
        from src.trader import trader
        sym = trade["symbol"]
        self.send(f"<b>{sym}</b> satis basliyor...")
        try:
            result = trader.sell(sym)
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
        from src.trader import trader
        positions = trader.get_positions()
        if not positions:
            self.send("Pozisyon yok.")
            return
        self.send(f"<b>HEPSINI SAT</b> ({len(positions)} coin)")
        results = trader.sell_all()
        for r in results:
            self.send(f"<b>{r['symbol']}</b> satildi  K/Z: ${r['pl']:+,.4f}")

    def _sell_one(self, coin):
        from src.trader import trader
        if not coin.endswith("/USD"):
            coin = coin + "/USD"
        pos = trader.get_position(coin)
        if not pos:
            self.send(f"<code>{coin}</code> pozisyon yok.")
            return
        try:
            result = trader.sell(coin)
            if result:
                self.send(f"<b>{coin}</b> satildi  K/Z: ${result['pl']:+,.4f}")
        except Exception as e:
            self.send(f"<b>{coin}</b> hata: {str(e)[:100]}")

    def send_buy_signal(self, symbol, confidence, price, reason, trade_id):
        with self._lock:
            self.pending[trade_id] = {
                "id": trade_id, "symbol": symbol, "action": "BUY",
                "confidence": confidence, "price": price, "reason": reason
            }
            self.send(f"<b>DEBUG</b> Sinyal kaydedildi: #{trade_id} {symbol}, bekleyen={list(self.pending.keys())}")

        msg = (
            f"<b>ALIS ONAY</b>  <code>{symbol}</code>\n\n"
            f"Fiyat: <code>${price:,.2f}</code>\n"
            f"Guven: <b>{confidence:.0%}</b>\n\n"
            f"<i>{reason}</i>\n\n"
            f"<code>yap</code> - al  |  <code>yapma</code> - alma\n"
            f"<code>yap {trade_id}</code> - #{trade_id} icin onay"
        )
        self.send(msg)

    def send_sell_signal(self, symbol, confidence, price, reason, trade_id, entry=0, pnl=0):
        with self._lock:
            self.pending_sell[trade_id] = {
                "id": trade_id, "symbol": symbol, "action": "SELL",
                "confidence": confidence, "price": price, "reason": reason,
                "pnl": pnl, "entry": entry
            }

        yuzde = ((price - entry) / entry * 100) if entry > 0 else 0
        kar_zarar = "KAR" if pnl > 0 else "ZARAR"
        msg = (
            f"<b>SATIS ONAY</b>  <code>{symbol}</code>\n\n"
            f"Giris: <code>${entry:,.2f}</code>  Simdi: <code>${price:,.2f}</code>\n"
            f"Degisim: <b>{yuzde:+.2f}%</b>  K/Z: <b>${pnl:+,.4f}</b> ({kar_zarar})\n\n"
            f"<i>{reason}</i>\n\n"
            f"<code>satis</code> - sat  |  <code>sakla</code> - tut"
        )
        self.send(msg)

    def send_ai_alert(self, symbol, direction, reason):
        emoji = "DUSER" if direction == "down" else "YUKSELI"
        msg = (
            f"<b>AI UYARISI</b>\n\n"
            f"<code>{symbol}</code> icin <b>{direction}</b> beklentisi\n"
            f"<i>{reason}</i>\n\n"
            f"Pozisyonlarinizi gozden gecirin."
        )
        self.send(msg)

    def _cmd_start(self):
        if self._on_start:
            self._on_start()
        self.send(
            f"<b>BOT BASLATILDI</b>\n\n"
            f"Coin: BTC, ETH\n"
            f"Miktar: ${settings.position_size_usd:.0f}\n"
            f"SL: %{settings.stop_loss_pct*100:.1f}  TP: %{settings.take_profit_pct*100:.1f}\n\n"
            f"Tarama basliyor...\n\n"
            f"/status - durum\n/pos - pozisyonlar\n/miktar - islem miktari\n/help - komutlar")

    def _cmd_stop(self):
        if self._on_stop:
            self._on_stop()
        self.send("<b>BOT DURDURULDU</b>")

    def _cmd_status(self):
        if self._on_status:
            data = self._on_status()
            if data:
                durum = "DURAKLATILDI" if data.get("paused") else "AKTIF" if data.get("running") else "DURDU"
                msg = (
                    f"<b>DURUM</b>\n\n"
                    f"Durum: <b>{durum}</b>\n"
                    f"Tarama: {data.get('total_scans', 0)}\n"
                    f"Sinyal: {data.get('signals_sent', 0)}\n"
                    f"Son: {data.get('last_scan', '-')}")
                if self.pending:
                    msg += f"\nBekleyen alis: {len(self.pending)}"
                if self.pending_sell:
                    msg += f"\nBekleyen satis: {len(self.pending_sell)}"
                self.send(msg)
            else:
                self.send("Bot calismiyor. /start ile baslatin.")
        else:
            self.send("Bot calismiyor. /start ile baslatin.")

    def _cmd_positions(self):
        from src.trader import trader
        positions = trader.get_positions()
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
        from src.trader import trader
        try:
            acc = trader.get_account()
            positions = trader.get_positions()
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
        if self._on_scan:
            self.send("Tarama basliyor...")
            threading.Thread(target=self._on_scan, daemon=True).start()
        else:
            self.send("Once /start lazim.")

    def _cmd_signals(self):
        if self._on_signals:
            signals = self._on_signals()
            if not signals:
                self.send("Sinyal yok.")
                return
            msg = "<b>SON SINYALLER</b>\n\n"
            for coin, sig in list(signals.items())[-10:]:
                islem = "ALIS" if sig["action"] == "BUY" else "SATIS"
                consensus = sig.get("consensus", 0)
                msg += f"<code>{coin:12s}</code> {islem}  ${sig['price']:,.2f}  {sig['confidence']:.0%}  Oy:{consensus}/5\n"
            self.send(msg)
        else:
            self.send("Sinyal yok.")

    def _cmd_memory(self):
        if self._on_memory:
            data = self._on_memory()
            stats = data.get("stats", {})
            ai = data.get("ai", {})
            recent = data.get("recent", [])
            predictions = data.get("predictions", [])
            msg = (
                f"<b>AI OGRENME</b>\n\n"
                f"<b>Strateji:</b>\n"
                f"Basari: <b>%{stats.get('win_rate', 0)}</b>\n"
                f"Toplam: {stats.get('total', 0)} islem\n"
                f"Kazanan: {stats.get('wins', 0)}  Kaybeden: {stats.get('losses', 0)}\n"
                f"Toplam K/Z: <code>${stats.get('total_pnl', 0):+,.4f}</code>\n\n"
            )
            model_durum = "HAZIR" if ai.get("model_ready") else f"Ogreniyor ({ai.get('model_samples', 0)} ornek)"
            msg += (
                f"<b>ML Model (GradientBoosting):</b>\n"
                f"Durum: {model_durum}\n"
                f"Ornek: {ai.get('model_samples', 0)}\n"
                f"Dogruluk: %{ai.get('accuracy', 0)*100:.1f}\n\n"
            )
            if predictions:
                msg += "<b>SON TAHMINLER</b>\n"
                for t in predictions[-5:]:
                    msg += f"<code>{t['symbol']:10s}</code> {t['action']:4s} ${t['price']:,.2f} Oy:{t.get('consensus', '-')}/6\n"
                msg += "\n"
            if recent:
                msg += "<b>SON ISLEMLER</b>\n"
                for t in recent[-5:]:
                    emoji = "WIN" if t.get("outcome") == "WIN" else "LOSS" if t.get("outcome") == "LOSS" else "---"
                    msg += f"<code>{t['symbol']:10s}</code> {t['action']:4s} ${t['price']:,.2f} {emoji} ${t.get('pnl', 0):+,.4f}\n"
            self.send(msg)
        else:
            self.send("AI hafiza bos.")

    def _cmd_pending(self):
        if not self.pending:
            self.send("Bekleyen alis yok.")
            return
        msg = "<b>BEKLEYEN ALISLAR</b>\n\n"
        for tid, trade in self.pending.items():
            msg += (
                f"#{tid} <code>{trade['symbol']}</code>\n"
                f"  ${trade['price']:,.2f}  Guven: {trade['confidence']:.0%}\n"
            )
        msg += "\nOnay: <code>yap</code> | Iptal: <code>yapma</code>"
        self.send(msg)

    def _cmd_pending_sells(self):
        if not self.pending_sell:
            self.send("Bekleyen satis yok.")
            return
        msg = "<b>BEKLEYEN SATISLAR</b>\n\n"
        for sid, sell in self.pending_sell.items():
            msg += (
                f"#{sid} <code>{sell['symbol']}</code>\n"
                f"  ${sell['price']:,.2f}  K/Z: ${sell.get('pnl', 0):+,.4f}\n"
            )
        msg += "\nOnay: <code>satis</code> | Iptal: <code>sakla</code>"
        self.send(msg)

    def _cmd_help(self):
        self.send(
            "<b>KOMUTLAR</b>\n\n"
            "<code>/start</code>  Baslat\n"
            "<code>/stop</code>   Durdur\n"
            "<code>/status</code> Durum\n"
            "<code>/pos</code>    Pozisyonlar\n"
            "<code>/balance</code> Bakiye\n"
            "<code>/scan</code>   Hemen tara\n"
            "<code>/signals</code> Sinyaller\n"
            "<code>/memory</code> AI ogrenme durumu\n"
            "<code>/onaylar</code> Bekleyen alislar\n\n"
            "<b>ISLEM MIKTARI</b>\n"
            "<code>/artir 50</code>  +$50 artir\n"
            "<code>/azalt 50</code>  -$50 azalt\n"
            "<code>/miktar</code>  Guncel miktar\n\n"
            "<b>ISLEM</b>\n"
            "<code>yap</code>  Alis onay\n"
            "<code>yapma</code>  Alis iptal\n"
            "<code>satis</code>  Satis onay\n"
            "<code>sakla</code>  Tut\n\n"
            "<b>SATIS</b>\n"
            "<code>sell BTC</code>  Tekil sat\n"
            "<code>sellall</code>  Hepini sat"
        )

    def _cmd_artir(self, arg):
        if not arg or not arg.isdigit():
            self.send("Kullanim: <code>/artir 50</code>")
            return
        amount = float(arg)
        settings.position_size_usd += amount
        self.send(f"<b>MIKTAR ARTTIRILDI</b>\n\nYeni: <code>${settings.position_size_usd:.0f}</code>")

    def _cmd_azalt(self, arg):
        if not arg or not arg.isdigit():
            self.send("Kullanim: <code>/azalt 50</code>")
            return
        amount = float(arg)
        if settings.position_size_usd - amount < 10:
            self.send("Minimum miktar: $10")
            return
        settings.position_size_usd -= amount
        self.send(f"<b>MIKTAR AZALTILDI</b>\n\nYeni: <code>${settings.position_size_usd:.0f}</code>")

    def _cmd_miktar(self):
        self.send(
            f"<b>ISLEM MIKTARI</b>\n\n"
            f"Guncel: <code>${settings.position_size_usd:.0f}</code>\n"
            f"Artir: <code>/artir 50</code>\n"
            f"Azalt: <code>/azalt 50</code>"
        )

    def poll(self):
        self.send("<b>DEBUG</b> Telegram dinleniyor...")
        self.running = True
        while self.running:
            try:
                for u in self.get_updates():
                    self.last_update_id = u["update_id"]
                    msg = u.get("message", {})
                    txt = msg.get("text", "")
                    cid = msg.get("chat", {}).get("id", "")
                    if txt:
                        self.handle(txt, cid)
            except Exception as e:
                self.send(f"<b>DEBUG</b> Hata: {str(e)[:50]}")
            time.sleep(2)

    def start_polling(self):
        threading.Thread(target=self.poll, daemon=True).start()

    def on_start(self, fn):
        self._on_start = fn

    def on_stop(self, fn):
        self._on_stop = fn

    def on_scan(self, fn):
        self._on_scan = fn

    def on_status(self, fn):
        self._on_status = fn

    def on_signals(self, fn):
        self._on_signals = fn

    def on_memory(self, fn):
        self._on_memory = fn


tg = TelegramBot()
