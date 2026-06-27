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

        # Onay komutlari
        if text in ["yap", "yap1", "evet", "onay", "1"]:
            self.handle_approval("yes")
            return
        if text in ["yapma", "hayir", "iptal", "0", "2"]:
            self.handle_approval("no")
            return

        # Sayili onay
        if text.startswith("yap ") or text.startswith("yap"):
            parts = text.split()
            if len(parts) > 1 and parts[1].isdigit():
                self.handle_approval("yes", int(parts[1]))
                return

        # Diger komutlar
        if text in ["/start", "start"]:
            self.cmd_start()
        elif text in ["/stop", "stop"]:
            self.cmd_stop()
        elif text in ["/status", "status"]:
            self.cmd_status()
        elif text in ["/signals", "signals"]:
            self.cmd_signals()
        elif text in ["/scan", "scan"]:
            self.cmd_scan()
        elif text in ["/help", "help", "/yardim"]:
            self.cmd_help()
        elif text in ["/onay", "onaylar"]:
            self.cmd_pending()
        elif text.startswith("/"):
            self.send_message(f"Bilinmeyen komut: {text}\nKomutlar icin /help yazin")

    def handle_approval(self, answer, trade_id=None):
        from src.main import bot

        if not self.pending_trades:
            self.send_message("Bekleyen islem yok.")
            return

        if trade_id:
            # Belirli bir islemi onayla
            if trade_id in self.pending_trades:
                trade = self.pending_trades.pop(trade_id)
                if answer == "yes":
                    self.execute_trade(trade)
                else:
                    self.send_message(f"<b>{trade['symbol']} - Islem iptal edildi</b>")
            else:
                self.send_message(f"#{trade_id} numarali islem bulunamadi.")
            return

        # Son islemi onayla
        last_id = max(self.pending_trades.keys()) if self.pending_trades else None
        if last_id is None:
            return

        trade = self.pending_trades.pop(last_id)
        if answer == "yes":
            self.execute_trade(trade)
        else:
            self.send_message(f"<b>{trade['symbol']} - Islem iptal edildi</b>")

    def execute_trade(self, trade):
        from src.main import bot
        if not bot:
            self.send_message("Bot calismiyor!")
            return

        symbol = trade["symbol"]
        action = trade["action"]
        price = trade["price"]

        self.send_message(f"<b>{symbol} - Islem baslatiliyor...</b>")

        try:
            if action == "BUY":
                qty = bot.client.calculate_qty(settings.position_size_usd, price)
                order = bot.client.place_market_order(
                    __import__('alpaca.trading.enums', fromlist=['OrderSide']).OrderSide.BUY,
                    qty, symbol
                )

                # Stop loss ve take profit
                stop_price = price * (1 - settings.stop_loss_pct)
                tp_price = price * (1 + settings.take_profit_pct)
                bot.client.place_stop_loss(qty, stop_price, symbol)
                bot.client.place_limit_order(
                    __import__('alpaca.trading.enums', fromlist=['OrderSide']).OrderSide.SELL,
                    qty, tp_price, symbol
                )

                self.send_message(
                    f"<b>{symbol} - ALIS TAMAM</b>\n\n"
                    f"Miktar: {qty:.6f}\n"
                    f"Fiyat: ${price:.4f}\n"
                    f"Stop Loss: ${stop_price:.4f}\n"
                    f"Take Profit: ${tp_price:.4f}"
                )

            elif action == "SELL":
                position = bot.client.get_position(symbol)
                if position:
                    qty = position["qty"]
                    bot.client.cancel_all_orders()
                    order = bot.client.place_market_order(
                        __import__('alpaca.trading.enums', fromlist=['OrderSide']).OrderSide.SELL,
                        qty, symbol
                    )
                    self.send_message(
                        f"<b>{symbol} - SATIS TAMAM</b>\n\n"
                        f"Miktar: {qty:.6f}\n"
                        f"Fiyat: ${price:.4f}"
                    )
                else:
                    self.send_message(f"{symbol} - Pozisyon bulunamadi!")

            bot.signals_sent += 1

        except Exception as e:
            self.send_message(f"<b>{symbol} - HATA</b>\n\n{str(e)}")

    def send_trade_signal(self, symbol, signal, position_info=None):
        islem = "ALIS" if signal.action == "BUY" else "SATIS"
        emoji = "BUY" if signal.action == "BUY" else "SELL"
        color = "BUY" if signal.action == "BUY" else "SELL"

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
            f"<b>[{emoji}] {symbol} - {islem}</b>\n\n"
            f"Fiyat: <b>${signal.price:,.4f}</b>\n"
            f"Guven: <b>{signal.confidence:.0%}</b>\n"
            f"RSI: {signal.rsi:.1f}\n"
            f"BB: ${signal.bb_lower:,.4f} - ${signal.bb_middle:,.4f} - ${signal.bb_upper:,.4f}\n"
            f"Hacim: {signal.volume_ratio:.1f}x\n"
            f"Degisim: {signal.price_change_pct*100:+.2f}%\n\n"
            f"<i>{signal.reason}</i>\n\n"
            f"<b>Islem yapmak icin:</b>\n"
            f"  yap - Onayla\n"
            f"  yapma - Iptal et\n"
            f"  onaylar - Bekleyenleri goster\n\n"
            f"#{trade_id}"
        )

        if position_info and position_info.get("qty", 0) > 0:
            text += (
                f"\n\nMevcut pozisyon: {position_info.get('qty', 0):.6f}\n"
                f"Giris: ${position_info.get('avg_entry_price', 0):,.4f}\n"
                f"K/Z: ${position_info.get('unrealized_pl', 0):+,.4f}"
            )

        self.send_message(text)
        return trade_id

    def cmd_start(self):
        from src.main import start_bot, bot
        if bot and bot.running:
            self.send_message("Bot zaten calisiyor!")
            return
        success = start_bot()
        if success:
            self.send_message(
                "<b>Bot baslatildi!</b>\n\n"
                f"Coin: {len(settings.symbols)}\n"
                f"Islem: ${settings.position_size_usd}\n"
                f"Aralk: {settings.check_interval}s\n\n"
                f"Sinyal geldiginde onay istenecek.\n"
                f"/help icin yardim"
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

        pending = len(self.pending_trades)

        text = (
            f"<b>DURUM</b>\n\n"
            f"Durum: <b>{durum}</b>\n"
            f"Tarama: <b>{bot.total_scans}</b>\n"
            f"Sinyal: <b>{bot.signals_sent}</b>\n"
            f"Coin: <b>{len(settings.symbols)}</b>\n"
            f"Son: <b>{bot.last_scan_time or '-'}</b>\n"
        )

        if pending > 0:
            text += f"\n<b>Bekleyen islem: {pending}</b>\n"
            for tid, trade in self.pending_trades.items():
                text += f"  #{tid} {trade['symbol']} - {trade['action']}\n"

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
            self.send_message("Bekleyen islem yok.")
            return

        text = "<b>BEKLEYEN ISLEMLER</b>\n\n"
        for tid, trade in self.pending_trades.items():
            islem = "ALIS" if trade["action"] == "BUY" else "SATIS"
            text += (
                f"#{tid} <b>{trade['symbol']}</b> - {islem}\n"
                f"  Fiyat: ${trade['price']:.4f}\n"
                f"  Guven: {trade['confidence']:.0%}\n"
                f"  {trade['time']}\n\n"
            )
        text += "Onaylamak icin: yap 1, yap 2, ...\nIptal icin: yapma"
        self.send_message(text)

    def cmd_help(self):
        self.send_message(
            "<b>KOMUTLAR</b>\n\n"
            "/start - Baslat\n"
            "/stop - Durdur\n"
            "/status - Durum\n"
            "/signals - Sinyaller\n"
            "/scan - Hemen tara\n"
            "/onaylar - Bekleyen islemler\n"
            "/help - Yardim\n\n"
            "<b>ISLEM ONAY</b>\n"
            "Sinyal geldiginde:\n"
            "  yap - Onayla\n"
            "  yapma - Iptal\n"
            "  yap 1 - #1'i onayla\n"
            "  onaylar - Listeyi goster"
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
        "Sinyal geldiginde onay istenecek.\n"
        "yap / yapma ile yanitla\n\n"
        "Komutlar icin /help"
    )
    return telegram_handler
