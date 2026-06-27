import sys
sys.path.insert(0, '.')
import requests
import time
import threading
from datetime import datetime
from src.config import settings


class TelegramBot:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.last_update_id = 0
        self.running = False
        self.pending_trades = {}
        self.pending_sells = {}
        self.last_trade_id = 0
        self._sent_ids = set()
        self._lock = threading.Lock()

    def send_message(self, text, parse_mode="HTML", silent=False):
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}
        if silent:
            payload["disable_notification"] = True
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except:
            return False

    def delete_message(self, msg_id):
        url = f"{self.base_url}/deleteMessage"
        try:
            requests.post(url, json={"chat_id": self.chat_id, "message_id": msg_id}, timeout=5)
        except:
            pass

    def edit_message(self, msg_id, text, parse_mode="HTML"):
        url = f"{self.base_url}/editMessageText"
        payload = {"chat_id": self.chat_id, "message_id": msg_id, "text": text, "parse_mode": parse_mode}
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except:
            return False

    def get_updates(self):
        url = f"{self.base_url}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 3}
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("result", [])
        except:
            pass
        return []

    def handle_message(self, text, chat_id):
        if str(chat_id) != str(self.chat_id):
            return

        text = text.strip()

        if text.lower() in ["satis", "satacak"]:
            self.handle_sell_approval("yes")
            return
        if text.lower() in ["sakla", "tut"]:
            self.handle_sell_approval("no")
            return

        parts = text.lower().split()
        if len(parts) == 2:
            cmd, arg = parts
            if cmd == "satis" and arg.isdigit():
                self.handle_sell_approval("yes", int(arg))
                return
            if cmd == "sakla" and arg.isdigit():
                self.handle_sell_approval("no", int(arg))
                return
            if cmd == "yap" and arg.isdigit():
                self.handle_approval("yes", int(arg))
                return
            if cmd == "sellt" and arg.isdigit():
                self.handle_sell_approval("yes", int(arg))
                return

        low = text.lower()
        if low in ["yap", "evet", "onay", "1"]:
            self.handle_approval("yes")
            return
        if low in ["yapma", "hayir", "iptal", "0", "2"]:
            self.handle_approval("no")
            return
        if low in ["sellall", "sell all", "hepsini sat", "tumu"]:
            self.cmd_sell_all()
            return

        if low.startswith("/"):
            self.route_command(low)

    def route_command(self, text):
        cmd = text.split()[0] if text else ""
        arg = text.split()[1] if len(text.split()) > 1 else ""

        if cmd in ["/start", "start"]:
            self.cmd_start()
        elif cmd in ["/stop", "stop"]:
            self.cmd_stop()
        elif cmd in ["/status", "status"]:
            self.cmd_status()
        elif cmd in ["/positions", "positions", "/pozisyon", "pozisyon", "pos"]:
            self.cmd_positions()
        elif cmd in ["/signals", "signals"]:
            self.cmd_signals()
        elif cmd in ["/scan", "scan"]:
            self.cmd_scan()
        elif cmd in ["/onaylar", "onaylar"]:
            self.cmd_pending()
        elif cmd in ["/satislar", "satislar"]:
            self.cmd_pending_sells()
        elif cmd in ["/sellall", "sellall"]:
            self.cmd_sell_all()
        elif cmd in ["/sell", "sell"] and arg:
            self.cmd_sell_coin(arg.upper())
        elif cmd in ["/balance", "balance", "/bakiye", "bakiye"]:
            self.cmd_balance()
        elif cmd in ["/help", "help", "/yardim"]:
            self.cmd_help()
        elif cmd.startswith("/"):
            self.send_message(f"Bilinmeyen: {cmd}\n/help")

    def handle_approval(self, answer, trade_id=None):
        with self._lock:
            if not self.pending_trades:
                self.send_message("Bekleyen alis yok.")
                return

            if trade_id:
                if trade_id in self.pending_trades:
                    trade = self.pending_trades.pop(trade_id)
                    if answer == "yes":
                        self.execute_buy(trade)
                    else:
                        self.send_message(f"<b>{trade['symbol']}</b> alis iptal edildi.")
                else:
                    self.send_message(f"#{trade_id} bulunamadi.")
                return

            last_id = max(self.pending_trades.keys()) if self.pending_trades else None
            if last_id is None:
                return

            trade = self.pending_trades.pop(last_id)
            if answer == "yes":
                self.execute_buy(trade)
            else:
                self.send_message(f"<b>{trade['symbol']}</b> alis iptal edildi.")

    def handle_sell_approval(self, answer, sell_id=None):
        with self._lock:
            if not self.pending_sells:
                self.send_message("Bekleyen satis yok.")
                return

            if sell_id:
                if sell_id in self.pending_sells:
                    sell = self.pending_sells.pop(sell_id)
                    if answer == "yes":
                        self.execute_sell(sell)
                    else:
                        self.send_message(f"<b>{sell['symbol']}</b> tutuluyor.")
                else:
                    self.send_message(f"#{sell_id} bulunamadi.")
                return

            last_id = max(self.pending_sells.keys()) if self.pending_sells else None
            if last_id is None:
                return

            sell = self.pending_sells.pop(last_id)
            if answer == "yes":
                self.execute_sell(sell)
            else:
                self.send_message(f"<b>{sell['symbol']}</b> tutuluyor.")

    def execute_buy(self, trade):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor!")
            return

        symbol = trade["symbol"]
        price = trade["price"]
        self.send_message(f"<b>{symbol}</b> alis baslatiliyor...")

        try:
            from alpaca.trading.enums import OrderSide
            qty = bot.client.calculate_qty(settings.position_size_usd, price)
            order = bot.client.place_market_order(OrderSide.BUY, qty, symbol)

            stop_price = price * (1 - settings.stop_loss_pct)
            tp_price = price * (1 + settings.take_profit_pct)
            bot.client.place_stop_loss(qty, stop_price, symbol)
            bot.client.place_limit_order(OrderSide.SELL, qty, tp_price, symbol)

            msg = (
                f"<b>ALIS TAMAM</b>  <code>{symbol}</code>\n"
                f"Miktar: <code>{qty:.6f}</code>\n"
                f"Fiyat: <code>${price:,.4f}</code>\n"
                f"SL: <code>${stop_price:,.4f}</code>  TP: <code>${tp_price:,.4f}</code>"
            )
            self.send_message(msg)
            bot.signals_sent += 1

        except Exception as e:
            self.send_message(f"<b>{symbol}</b> hata:\n<code>{str(e)[:200]}</code>")

    def execute_sell(self, sell):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor!")
            return

        symbol = sell["symbol"]
        self.send_message(f"<b>{symbol}</b> satis baslatiliyor...")

        try:
            from alpaca.trading.enums import OrderSide
            position = bot.client.get_position(symbol)
            if position:
                qty = position["qty"]
                bot.client.cancel_all_orders()
                order = bot.client.place_market_order(OrderSide.SELL, qty, symbol)
                pl = sell.get("unrealized_pl", 0)
                msg = (
                    f"<b>SATIS TAMAM</b>  <code>{symbol}</code>\n"
                    f"Miktar: <code>{qty:.6f}</code>\n"
                    f"Fiyat: <code>${sell['price']:,.4f}</code>\n"
                    f"K/Z: <code>${pl:+,.4f}</code>"
                )
                self.send_message(msg)
                bot.signals_sent += 1
            else:
                self.send_message(f"<b>{symbol}</b> pozisyon bulunamadi.")
        except Exception as e:
            self.send_message(f"<b>{symbol}</b> hata:\n<code>{str(e)[:200]}</code>")

    def send_buy_signal(self, symbol, signal, position_info=None):
        with self._lock:
            sig_key = f"BUY_{symbol}"
            if sig_key in self._sent_ids:
                return None
            self._sent_ids.add(sig_key)
            if len(self._sent_ids) > 200:
                self._sent_ids.clear()

            self.last_trade_id += 1
            trade_id = self.last_trade_id

            self.pending_trades[trade_id] = {
                "id": trade_id, "symbol": symbol, "action": signal.action,
                "price": signal.price, "confidence": signal.confidence,
                "reason": signal.reason, "time": datetime.now().strftime('%H:%M:%S')
            }

        msg = (
            f"<b>ALIS ONAY</b>  <code>{symbol}</code>\n\n"
            f"Fiyat: <code>${signal.price:,.4f}</code>\n"
            f"Guven: <b>{signal.confidence:.0%}</b>\n"
            f"RSI: {signal.rsi:.1f}  Hacim: {signal.volume_ratio:.1f}x\n\n"
            f"<i>{signal.reason}</i>\n\n"
            f"<code>yap</code> - al  |  <code>yapma</code> - alma"
        )

        if position_info and position_info.get("qty", 0) > 0:
            msg += f"\nPozisyon: {position_info['qty']:.6f} @ ${position_info.get('avg_entry_price', 0):,.4f}"

        self.send_message(msg)
        return trade_id

    def send_sell_signal(self, symbol, signal, position_info):
        with self._lock:
            sig_key = f"SELL_{symbol}"
            if sig_key in self._sent_ids:
                return None
            self._sent_ids.add(sig_key)
            if len(self._sent_ids) > 200:
                self._sent_ids.clear()

            self.last_trade_id += 1
            sell_id = self.last_trade_id

            pl = position_info.get("unrealized_pl", 0) if position_info else 0
            entry = position_info.get("avg_entry_price", 0) if position_info else 0

            self.pending_sells[sell_id] = {
                "id": sell_id, "symbol": symbol, "action": "SELL",
                "price": signal.price, "confidence": signal.confidence,
                "reason": signal.reason, "unrealized_pl": pl,
                "time": datetime.now().strftime('%H:%M:%S')
            }

        yuzde = ((signal.price - entry) / entry * 100) if entry > 0 else 0
        kar_zarar = "KAR" if pl > 0 else "ZARAR"

        msg = (
            f"<b>SATIS ONAY</b>  <code>{symbol}</code>\n\n"
            f"Giris: <code>${entry:,.4f}</code>  Simdi: <code>${signal.price:,.4f}</code>\n"
            f"Degisim: <b>{yuzde:+.2f}%</b>  K/Z: <b>${pl:+,.4f}</b> ({kar_zarar})\n\n"
            f"RSI: {signal.rsi:.1f}\n"
            f"<i>{signal.reason}</i>\n\n"
            f"<code>satis</code> - sat  |  <code>sakla</code> - tut"
        )

        self.send_message(msg)
        return sell_id

    def cmd_sell_all(self):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor.")
            return

        positions = bot.client.get_positions()
        if not positions:
            self.send_message("Pozisyon yok.")
            return

        self.send_message(f"<b>HEPSINI SAT</b>  ({len(positions)} pozisyon)")

        for p in positions:
            try:
                from alpaca.trading.enums import OrderSide
                symbol = p["symbol"]
                qty = p["qty"]
                bot.client.cancel_all_orders()
                bot.client.place_market_order(OrderSide.SELL, qty, symbol)
                pl = p.get("unrealized_pl", 0)
                self.send_message(f"<b>{symbol}</b> satildi  K/Z: ${pl:+,.4f}")
            except Exception as e:
                self.send_message(f"<b>{p['symbol']}</b> hata: {str(e)[:100]}")

    def cmd_sell_coin(self, coin):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor.")
            return

        if not coin.endswith("/USD"):
            coin = coin + "/USD"

        position = bot.client.get_position(coin)
        if not position:
            self.send_message(f"<code>{coin}</code> pozisyon yok.")
            return

        try:
            from alpaca.trading.enums import OrderSide
            symbol = position["symbol"]
            qty = position["qty"]
            pl = position.get("unrealized_pl", 0)
            bot.client.cancel_all_orders()
            bot.client.place_market_order(OrderSide.SELL, qty, symbol)
            self.send_message(f"<b>{symbol}</b> satildi  K/Z: ${pl:+,.4f}")
        except Exception as e:
            self.send_message(f"<b>{coin}</b> hata: {str(e)[:100]}")

    def cmd_balance(self):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor.")
            return

        try:
            acc = bot.client.get_account()
            positions = bot.client.get_positions()
            toplam_kz = sum(p.get("unrealized_pl", 0) for p in positions)
            toplam_deger = sum(p.get("market_value", 0) for p in positions)

            msg = (
                f"<b>BAKIYE</b>\n\n"
                f"Portfoy: <code>${float(acc.portfolio_value):,.2f}</code>\n"
                f"Nakit: <code>${float(acc.cash):,.2f}</code>\n"
                f"Pozisyon: <code>${toplam_deger:,.2f}</code>\n"
                f"Acik K/Z: <code>${toplam_kz:+,.4f}</code>\n"
                f"Pozisyon sayisi: <b>{len(positions)}</b>"
            )
            self.send_message(msg)
        except Exception as e:
            self.send_message(f"Hata: {str(e)[:100]}")

    def cmd_positions(self):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor.")
            return

        positions = bot.client.get_positions()
        if not positions:
            self.send_message(
                "<b>POZISYONLAR</b>\n\n"
                "Acik pozisyon yok.\n\n"
                "Tarama icin /scan"
            )
            return

        msg = "<b>POZISYONLAR</b>\n\n"
        toplam = 0
        for p in positions:
            sym = p["symbol"]
            entry = p["avg_entry_price"]
            mv = p["market_value"]
            pl = p["unrealized_pl"]
            toplam += pl
            yuzde = ((mv - entry * p["qty"]) / (entry * p["qty"]) * 100) if entry > 0 else 0

            msg += (
                f"<code>{sym}</code>\n"
                f"  {p['qty']:.6f} @ ${entry:,.4f}\n"
                f"  Deger: ${mv:,.2f}\n"
                f"  K/Z: ${pl:+,.4f} ({yuzde:+.1f}%)\n\n"
            )

        msg += f"Toplam K/Z: <b>${toplam:+,.4f}</b>\n\n"
        msg += "Sat: <code>sell BTC</code>  Hep: <code>sellall</code>"
        self.send_message(msg)

    def cmd_start(self):
        from src.main import start_bot, bot
        if bot and bot.running:
            self.send_message("Bot zaten calisiyor!")
            return
        success = start_bot()
        if success:
            self.send_message(
                f"<b>BOT BASLATILDI</b>\n\n"
                f"Coin: 7  |  Islem: ${settings.position_size_usd}\n"
                f"Hedef: Gunluk %5\n"
                f"SL: %{settings.stop_loss_pct*100:.1f}  TP: %{settings.take_profit_pct*100:.1f}\n\n"
                f"Pozisyonlar: /pos\n"
                f"Bakiye: /balance\n"
                f"Komutlar: /help"
            )
        else:
            self.send_message("Basarisiz!")

    def cmd_stop(self):
        from src.main import stop_bot, bot
        if not bot or not bot.running:
            self.send_message("Bot zaten durdu!")
            return
        stop_bot()
        self.send_message("<b>BOT DURDURULDU</b>")

    def cmd_status(self):
        from src.main import bot
        if not bot or not bot.running:
            self.send_message("Bot calismiyor. /start ile baslatin.")
            return

        durum = "DURAKLATILDI" if bot.paused else "AKTIF"
        msg = (
            f"<b>DURUM</b>\n\n"
            f"Durum: <b>{durum}</b>\n"
            f"Tarama: {bot.total_scans}  |  Sinyal: {bot.signals_sent}\n"
            f"Coin: {len(settings.symbols)}\n"
            f"Son: {bot.last_scan_time or '-'}\n"
        )

        if self.pending_trades:
            msg += f"\nBekleyen alis: {len(self.pending_trades)}"
        if self.pending_sells:
            msg += f"\nBekleyen satis: {len(self.pending_sells)}"

        self.send_message(msg)

    def cmd_signals(self):
        from src.main import bot
        if not bot or not bot.last_signals:
            self.send_message("Sinyal yok.")
            return

        msg = "<b>SON SINYALLER</b>\n\n"
        for coin, sig in list(bot.last_signals.items())[-10:]:
            islem = "ALIS" if sig.action == "BUY" else "SATIS"
            msg += f"<code>{coin:12s}</code> {islem}  ${sig.price:,.4f}  {sig.confidence:.0%}\n"
        self.send_message(msg)

    def cmd_scan(self):
        from src.main import bot
        if not bot:
            self.send_message("Once /start lazim.")
            return
        self.send_message("Tarama basliyor...")
        t = threading.Thread(target=bot.run_iteration, daemon=True)
        t.start()

    def cmd_pending(self):
        if not self.pending_trades:
            self.send_message("Bekleyen alis yok.")
            return

        msg = "<b>BEKLEYEN ALISLAR</b>\n\n"
        for tid, trade in self.pending_trades.items():
            msg += (
                f"#{tid} <code>{trade['symbol']}</code>\n"
                f"  ${trade['price']:,.4f}  Guven: {trade['confidence']:.0%}\n"
            )
        msg += "\nOnay: <code>yap</code> | Iptal: <code>yapma</code>"
        self.send_message(msg)

    def cmd_pending_sells(self):
        if not self.pending_sells:
            self.send_message("Bekleyen satis yok.")
            return

        msg = "<b>BEKLEYEN SATISLAR</b>\n\n"
        for sid, sell in self.pending_sells.items():
            msg += (
                f"#{sid} <code>{sell['symbol']}</code>\n"
                f"  ${sell['price']:,.4f}  K/Z: ${sell.get('unrealized_pl', 0):+,.4f}\n"
            )
        msg += "\nOnay: <code>satis</code> | Iptal: <code>sakla</code>"
        self.send_message(msg)

    def cmd_help(self):
        self.send_message(
            "<b>KOMUTLAR</b>\n\n"
            "<code>/start</code>  Baslat\n"
            "<code>/stop</code>   Durdur\n"
            "<code>/status</code> Durum\n"
            "<code>/pos</code>    Pozisyonlar\n"
            "<code>/balance</code> Bakiye\n"
            "<code>/scan</code>   Hemen tara\n"
            "<code>/signals</code> Sinyaller\n"
            "<code>/onaylar</code> Bekleyen alislar\n\n"
            "<b>ISLEM</b>\n"
            "<code>yap</code>  Alis onay\n"
            "<code>yapma</code>  Alis iptal\n"
            "<code>satis</code>  Satis onay\n"
            "<code>sakla</code>  Tut\n\n"
            "<b>SATIS</b>\n"
            "<code>sell BTC</code>  Tekil sat\n"
            "<code>sellall</code>  Hepini sat\n"
            "<code>/pos</code>  Pozisyon listesi"
        )

    def poll(self):
        print("[TG] Telegram dinleniyor...")
        self.running = True
        while self.running:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id", "")
                    if text:
                        print(f"[TG] {text}")
                        self.handle_message(text, chat_id)
            except Exception as e:
                print(f"[TG] Hata: {e}")
            time.sleep(2)

    def start_polling(self):
        t = threading.Thread(target=self.poll, daemon=True)
        t.start()
        return t


telegram_handler = None


def init_telegram():
    global telegram_handler
    telegram_handler = TelegramBot(settings.telegram_bot_token, settings.telegram_chat_id)
    telegram_handler.start_polling()
    telegram_handler.send_message(
        f"<b>SISTEM HAZIR</b>\n\n"
        f"Coin: 7  |  Hedef: Gunluk %5\n\n"
        f"Basla: <code>/start</code>\n"
        f"Komutlar: <code>/help</code>"
    )
    return telegram_handler
