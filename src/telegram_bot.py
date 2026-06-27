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

    def send_message(self, text, parse_mode="HTML"):
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}
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

        text = text.strip().lower()

        # Satis onay
        if text in ["satis", "satis1", "satacak"]:
            self.handle_sell_approval("yes")
            return
        if text in ["sakla", "sakla1", "tut"]:
            self.handle_sell_approval("no")
            return

        if text.startswith("satis ") and len(text.split()) > 1 and text.split()[1].isdigit():
            self.handle_sell_approval("yes", int(text.split()[1]))
            return
        if text.startswith("sakla ") and len(text.split()) > 1 and text.split()[1].isdigit():
            self.handle_sell_approval("no", int(text.split()[1]))
            return

        # Alis onay
        if text in ["yap", "yap1", "evet", "onay", "1"]:
            self.handle_approval("yes")
            return
        if text in ["yapma", "hayir", "iptal", "0", "2"]:
            self.handle_approval("no")
            return

        if text.startswith("yap ") and len(text.split()) > 1 and text.split()[1].isdigit():
            self.handle_approval("yes", int(text.split()[1]))
            return

        # Komutlar
        if text in ["/start", "start"]:
            self.cmd_start()
        elif text in ["/stop", "stop"]:
            self.cmd_stop()
        elif text in ["/status", "status"]:
            self.cmd_status()
        elif text in ["/signals", "signals"]:
            self.cmd_signals()
        elif text in ["/positions", "positions", "/pozisyon", "pozisyon", "pos"]:
            self.cmd_positions()
        elif text in ["/scan", "scan"]:
            self.cmd_scan()
        elif text in ["/onaylar", "onaylar"]:
            self.cmd_pending()
        elif text in ["/satislar", "satislar"]:
            self.cmd_pending_sells()
        elif text in ["/help", "help", "/yardim"]:
            self.cmd_help()
        elif text.startswith("/"):
            self.send_message(f"Bilinmeyen komut: {text}\nKomutlar icin /help")

    def handle_approval(self, answer, trade_id=None):
        if not self.pending_trades:
            self.send_message("Bekleyen alis islemi yok.")
            return

        if trade_id:
            if trade_id in self.pending_trades:
                trade = self.pending_trades.pop(trade_id)
                if answer == "yes":
                    self.execute_buy(trade)
                else:
                    self.send_message(f"<b>{trade['symbol']} - Alis iptal</b>")
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
            self.send_message(f"<b>{trade['symbol']} - Alis iptal</b>")

    def handle_sell_approval(self, answer, sell_id=None):
        if not self.pending_sells:
            self.send_message("Bekleyen satis islemi yok.")
            return

        if sell_id:
            if sell_id in self.pending_sells:
                sell = self.pending_sells.pop(sell_id)
                if answer == "yes":
                    self.execute_sell(sell)
                else:
                    self.send_message(f"<b>{sell['symbol']} - Satis iptal, tutuluyor</b>")
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
            self.send_message(f"<b>{sell['symbol']} - Satis iptal, tutuluyor</b>")

    def execute_buy(self, trade):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor!")
            return

        symbol = trade["symbol"]
        price = trade["price"]

        self.send_message(f"<b>{symbol} - Alis baslatiliyor...</b>")

        try:
            from alpaca.trading.enums import OrderSide
            qty = bot.client.calculate_qty(settings.position_size_usd, price)
            order = bot.client.place_market_order(OrderSide.BUY, qty, symbol)

            stop_price = price * (1 - settings.stop_loss_pct)
            tp_price = price * (1 + settings.take_profit_pct)
            bot.client.place_stop_loss(qty, stop_price, symbol)
            bot.client.place_limit_order(OrderSide.SELL, qty, tp_price, symbol)

            self.send_message(
                f"<b>{symbol} - ALIS TAMAM</b>\n\n"
                f"Miktar: {qty:.6f}\n"
                f"Fiyat: ${price:.4f}\n"
                f"Stop Loss: ${stop_price:.4f}\n"
                f"Take Profit: ${tp_price:.4f}\n\n"
                f"Pozisyon icin /pozisyon yazin"
            )
            bot.signals_sent += 1

        except Exception as e:
            self.send_message(f"<b>{symbol} - HATA</b>\n\n{str(e)}")

    def execute_sell(self, sell):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor!")
            return

        symbol = sell["symbol"]

        self.send_message(f"<b>{symbol} - Satis baslatiliyor...</b>")

        try:
            from alpaca.trading.enums import OrderSide
            position = bot.client.get_position(symbol)
            if position:
                qty = position["qty"]
                bot.client.cancel_all_orders()
                order = bot.client.place_market_order(OrderSide.SELL, qty, symbol)
                pl = sell.get("unrealized_pl", 0)
                self.send_message(
                    f"<b>{symbol} - SATIS TAMAM</b>\n\n"
                    f"Miktar: {qty:.6f}\n"
                    f"Fiyat: ${sell['price']:.4f}\n"
                    f"K/Z: ${pl:+,.4f}\n\n"
                    f"Pozisyon icin /pozisyon yazin"
                )
                bot.signals_sent += 1
            else:
                self.send_message(f"{symbol} - Pozisyon bulunamadi!")
        except Exception as e:
            self.send_message(f"<b>{symbol} - HATA</b>\n\n{str(e)}")

    def send_buy_signal(self, symbol, signal, position_info=None):
        self.last_trade_id += 1
        trade_id = self.last_trade_id

        self.pending_trades[trade_id] = {
            "id": trade_id,
            "symbol": symbol,
            "action": signal.action,
            "price": signal.price,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "time": datetime.now().strftime('%H:%M:%S')
        }

        text = (
            f"<b>[BUY] {symbol} - ALIS ONAYI</b>\n\n"
            f"Fiyat: <b>${signal.price:,.4f}</b>\n"
            f"Guven: <b>{signal.confidence:.0%}</b>\n"
            f"RSI: {signal.rsi:.1f}\n"
            f"Hacim: {signal.volume_ratio:.1f}x\n"
            f"Degisim: {signal.price_change_pct*100:+.2f}%\n\n"
            f"<i>{signal.reason}</i>\n\n"
            f"<b>Onay:\n"
            f"  yap - Al\n"
            f"  yapma - Alma</b>\n\n"
            f"#{trade_id}"
        )

        if position_info and position_info.get("qty", 0) > 0:
            text += (
                f"\nMevcut: {position_info.get('qty', 0):.6f} @ "
                f"${position_info.get('avg_entry_price', 0):,.4f}"
            )

        self.send_message(text)
        return trade_id

    def send_sell_signal(self, symbol, signal, position_info):
        self.last_trade_id += 1
        sell_id = self.last_trade_id

        pl = position_info.get("unrealized_pl", 0) if position_info else 0
        entry = position_info.get("avg_entry_price", 0) if position_info else 0
        qty = position_info.get("qty", 0) if position_info else 0

        self.pending_sells[sell_id] = {
            "id": sell_id,
            "symbol": symbol,
            "action": "SELL",
            "price": signal.price,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "unrealized_pl": pl,
            "time": datetime.now().strftime('%H:%M:%S')
        }

        kar_zarar = "KAR" if pl > 0 else "ZARAR"
        yuzde = ((signal.price - entry) / entry * 100) if entry > 0 else 0

        text = (
            f"<b>[SELL] {symbol} - SATIS ONAYI</b>\n\n"
            f"Giris: <b>${entry:,.4f}</b>\n"
            f"Simdi: <b>${signal.price:,.4f}</b>\n"
            f"Degisim: <b>{yuzde:+.2f}%</b>\n"
            f"K/Z: <b>${pl:+,.4f}</b> ({kar_zarar})\n\n"
            f"Guven: <b>{signal.confidence:.0%}</b>\n"
            f"RSI: {signal.rsi:.1f}\n"
            f"Sebep: <i>{signal.reason}</i>\n\n"
            f"<b>Onay:\n"
            f"  satis - SAT\n"
            f"  sakla - TUT</b>\n\n"
            f"#{sell_id}"
        )

        self.send_message(text)
        return sell_id

    def cmd_positions(self):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor.")
            return

        try:
            positions = bot.client.get_positions()
            if not positions:
                self.send_message(
                    "<b>POZISYONLAR</b>\n\n"
                    "Acik pozisyon yok.\n\n"
                    "Yeni islem icin /scan yapin"
                )
                return

            text = "<b>POZISYONLAR</b>\n\n"
            toplam = 0
            for p in positions:
                sym = p["symbol"]
                qty = p["qty"]
                entry = p["avg_entry_price"]
                mv = p["market_value"]
                pl = p["unrealized_pl"]
                toplam += pl

                durum = "KAR" if pl > 0 else "ZARAR"
                emoji = "+" if pl > 0 else ""
                yuzde = ((mv - entry * qty) / (entry * qty) * 100) if entry > 0 and qty > 0 else 0

                text += (
                    f"<b>{sym}</b>\n"
                    f"  Miktar: {qty:.6f}\n"
                    f"  Giris: ${entry:,.4f}\n"
                    f"  Deger: ${mv:,.2f}\n"
                    f"  K/Z: ${emoji}{pl:,.4f} ({durum} {yuzde:+.1f}%)\n\n"
                )

            text += f"<b>Toplam K/Z: ${toplam:+,.4f}</b>"
            self.send_message(text)

        except Exception as e:
            self.send_message(f"<b>HATA</b>\n\n{str(e)}")

    def cmd_start(self):
        from src.main import start_bot, bot
        if bot and bot.running:
            self.send_message("Bot zaten calisiyor!")
            return
        success = start_bot()
        if success:
            self.send_message(
                "<b>Bot baslatildi!</b>\n\n"
                f"Coin: {len(settings.symbols)} (7 secili)\n"
                f"Islem: ${settings.position_size_usd}/islem\n"
                f"Hedef: Gunluk %5 kar\n"
                f"Max Pozisyon: {settings.max_positions}\n\n"
                "Sinyal geldiginde onay istenecek.\n"
                "/help icin yardim"
            )
        else:
            self.send_message("Basarisiz! API kontrol edin.")

    def cmd_stop(self):
        from src.main import stop_bot, bot
        if not bot or not bot.running:
            self.send_message("Bot zaten durdu!")
            return
        stop_bot()
        self.send_message("<b>Bot durduruldu!</b>")

    def cmd_status(self):
        from src.main import bot
        if not bot or not bot.running:
            self.send_message("Bot calismiyor. /start ile baslatin.")
            return

        durum = "CALISIYOR"
        if bot.paused:
            durum = "DURAKLATILDI"

        text = (
            f"<b>DURUM</b>\n\n"
            f"Durum: <b>{durum}</b>\n"
            f"Tarama: <b>{bot.total_scans}</b>\n"
            f"Sinyal: <b>{bot.signals_sent}</b>\n"
            f"Coin: <b>{len(settings.symbols)} (7 secili)</b>\n"
            f"Islem: <b>${settings.position_size_usd}</b>\n"
            f"Hedef: <b>Gunluk %5</b>\n"
            f"Max Pozisyon: <b>{settings.max_positions}</b>\n"
            f"Son: <b>{bot.last_scan_time or '-'}</b>\n"
        )

        if self.pending_trades:
            text += f"\n<b>Bekleyen alis: {len(self.pending_trades)}</b>\n"
        if self.pending_sells:
            text += f"<b>Bekleyen satis: {len(self.pending_sells)}</b>\n"

        self.send_message(text)

    def cmd_signals(self):
        from src.main import bot
        if not bot or not bot.last_signals:
            self.send_message("Sinyal yok.")
            return

        text = "<b>SON SINYALLER</b>\n\n"
        for coin, sig in list(bot.last_signals.items())[-10:]:
            islem = "ALIS" if sig.action == "BUY" else "SATIS"
            text += f"<b>{coin}</b> - {islem} (${sig.price:.4f}) {sig.confidence:.0%}\n"
        self.send_message(text)

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

        text = "<b>BEKLEYEN ALISLAR</b>\n\n"
        for tid, trade in self.pending_trades.items():
            text += (
                f"#{tid} <b>{trade['symbol']}</b>\n"
                f"  Fiyat: ${trade['price']:.4f}\n"
                f"  Guven: {trade['confidence']:.0%}\n"
                f"  {trade['time']}\n\n"
            )
        text += "Onay: yap 1, yap 2\nIptal: yapma"
        self.send_message(text)

    def cmd_pending_sells(self):
        if not self.pending_sells:
            self.send_message("Bekleyen satis yok.")
            return

        text = "<b>BEKLEYEN SATISLAR</b>\n\n"
        for sid, sell in self.pending_sells.items():
            text += (
                f"#{sid} <b>{sell['symbol']}</b>\n"
                f"  Fiyat: ${sell['price']:.4f}\n"
                f"  Guven: {sell['confidence']:.0%}\n"
                f"  K/Z: ${sell.get('unrealized_pl', 0):+,.4f}\n"
                f"  {sell['time']}\n\n"
            )
        text += "Satis: satis 1\nSakla: sakla 1"
        self.send_message(text)

    def cmd_help(self):
        self.send_message(
            "<b>KOMUTLAR</b>\n\n"
            "/start - Baslat\n"
            "/stop - Durdur\n"
            "/status - Durum\n"
            "/positions - Pozisyonlar\n"
            "/signals - Sinyaller\n"
            "/scan - Hemen tara\n"
            "/onaylar - Bekleyen alislar\n"
            "/satislar - Bekleyen satislar\n"
            "/help - Yardim\n\n"
            "<b>ISLEM ONAY</b>\n"
            "Alis: yap / yapma\n"
            "Satis: satis / sakla\n"
            "Sirali: yap 1, satis 2"
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
        "<b>Bot hazir!</b>\n\n"
        "Alis onayi: yap / yapma\n"
        "Satis onayi: satis / sakla\n"
        "Pozisyonlar: /positions\n\n"
        "Komutlar icin /help"
    )
    return telegram_handler
