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
        self.bot_ref = None

    def send_message(self, text, parse_mode="HTML"):
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            print(f"[TG] Gonderme hatasi: {e}")
            return False

    def get_updates(self):
        url = f"{self.base_url}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 3}
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", [])
        except Exception as e:
            print(f"[TG] Update hatasi: {e}")
        return []

    def handle_message(self, text, chat_id):
        if str(chat_id) != str(self.chat_id):
            return

        text = text.strip().lower()

        if text == "/start" or text == "start":
            self.cmd_start()
        elif text == "/stop" or text == "stop":
            self.cmd_stop()
        elif text == "/status" or text == "status":
            self.cmd_status()
        elif text == "/signals" or text == "signals":
            self.cmd_signals()
        elif text == "/scan" or text == "scan":
            self.cmd_scan()
        elif text == "/help" or text == "help" or text == "/yardim":
            self.cmd_help()
        elif text.startswith("/"):
            self.send_message(f"Bilinmeyen komut: {text}\nKomutlar icin /help yazin")

    def cmd_start(self):
        from src.main import start_bot, bot
        if bot and bot.running:
            self.send_message("Bot zaten calisiyor!\nDurum: CALISIYOR")
            return

        success = start_bot()
        if success:
            time.sleep(1)
            self.send_message(
                "<b>Bot baslatildi!</b>\n\n"
                f"Coin sayisi: {len(settings.symbols)}\n"
                f"Tarama araligi: {settings.check_interval} saniye\n"
                f"Pozisyon boyutu: ${settings.position_size_usd}\n\n"
                f"Durum icin /status yazin"
            )
        else:
            self.send_message("Bot baslatilamadi!\nAPI baglantisi kontrol edin.")

    def cmd_stop(self):
        from src.main import stop_bot, bot
        if not bot or not bot.running:
            self.send_message("Bot zaten durdurulmus!")
            return

        stop_bot()
        self.send_message("<b>Bot durduruldu!</b>")

    def cmd_status(self):
        from src.main import bot
        if not bot or not bot.running:
            self.send_message("Bot calismiyor.\nBaslatmak icin /start yazin.")
            return

        durum = "CALISIYOR"
        if bot.paused:
            durum = "DURAKLATILDI"

        text = (
            f"<b>DURUM</b>\n\n"
            f"Durum: <b>{durum}</b>\n"
            f"Toplam tarama: <b>{bot.total_scans}</b>\n"
            f"Gonderilen sinyal: <b>{bot.signals_sent}</b>\n"
            f"Son tarama: <b>{bot.last_scan_time or '-'}</b>\n"
            f"Coin sayisi: <b>{len(settings.symbols)}</b>\n"
        )

        if bot.last_signals:
            text += "\n<b>Son sinyaller:</b>\n"
            for coin, sig in list(bot.last_signals.items())[-5:]:
                islem = "ALIS" if sig.action == "BUY" else "SATIS"
                text += f"  {coin} - {islem} (${sig.price:.4f})\n"

        self.send_message(text)

    def cmd_signals(self):
        from src.main import bot
        if not bot or not bot.last_signals:
            self.send_message("Henuz sinyal yok.\nTarama bekleniyor...")
            return

        text = "<b>SON SINYALLER</b>\n\n"
        for coin, sig in list(bot.last_signals.items())[-10:]:
            islem = "ALIS" if sig.action == "BUY" else "SATIS"
            renk = "+" if sig.action == "BUY" else "-"
            text += (
                f"<b>{coin}</b> - {islem}\n"
                f"  Fiyat: ${sig.price:.4f}\n"
                f"  Guven: {sig.confidence:.0%}\n"
                f"  RSI: {sig.rsi:.1f}\n\n"
            )
        self.send_message(text)

    def cmd_scan(self):
        from src.main import bot
        if not bot:
            self.send_message("Once /start ile botu baslatin.")
            return

        self.send_message("Tarama baslatildi... Lutfen bekleyin (30-60 sn)")

        def run_scan():
            bot.run_iteration()

        t = threading.Thread(target=run_scan, daemon=True)
        t.start()

    def cmd_help(self):
        self.send_message(
            "<b>KOMUTLAR</b>\n\n"
            "/start - Botu baslat\n"
            "/stop - Botu durdur\n"
            "/status - Durum goster\n"
            "/signals - Son sinyaller\n"
            "/scan - Hemen tara\n"
            "/help - Bu mesaj\n\n"
            f"Toplam <b>{len(settings.symbols)}</b> coin taraniyor"
        )

    def poll(self):
        print("[TG] Telegram botu dinleniyor...")
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
                        print(f"[TG] Mesaj: {text} (chat: {chat_id})")
                        self.handle_message(text, chat_id)
            except Exception as e:
                print(f"[TG] Polling hatasi: {e}")
            time.sleep(2)

    def start_polling(self):
        thread = threading.Thread(target=self.poll, daemon=True)
        thread.start()
        return thread


telegram_handler = None


def init_telegram():
    global telegram_handler
    telegram_handler = TelegramBot(settings.telegram_bot_token, settings.telegram_chat_id)
    telegram_handler.start_polling()
    telegram_handler.send_message(
        "<b>Bot hazir!</b>\n\n"
        "Komutlar:\n"
        "/start - Baslat\n"
        "/stop - Durdur\n"
        "/status - Durum\n"
        "/signals - Sinyaller\n"
        "/help - Yardim"
    )
    return telegram_handler
