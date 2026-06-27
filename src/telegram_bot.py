import sys
sys.path.insert(0, '.')
import requests
import json
from datetime import datetime
from src.config import settings


class TelegramBot:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.last_update_id = 0
        self.commands = {
            "/start": self.cmd_start,
            "/stop": self.cmd_stop,
            "/status": self.cmd_status,
            "/signals": self.cmd_signals,
            "/scan": self.cmd_scan,
            "/help": self.cmd_help,
        }

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
        params = {"offset": self.last_update_id + 1, "timeout": 1}
        try:
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", [])
        except:
            pass
        return []

    def poll_commands(self, bot_instance):
        updates = self.get_updates()
        for update in updates:
            self.last_update_id = update["update_id"]
            msg = update.get("message", {})
            text = msg.get("text", "").strip().lower()
            chat_id = str(msg.get("chat", {}).get("id", ""))

            if chat_id != self.chat_id:
                continue

            if text in self.commands:
                self.commands[text](bot_instance)
            elif text.startswith("/"):
                self.send_message(f"Bilinmeyen komut: {text}\n/Yardim icin /help yazin")

    def cmd_start(self, bot_instance):
        if bot_instance and bot_instance.running:
            self.send_message("Bot zaten calisiyor!")
            return

        from src.main import start_bot
        success = start_bot()
        if success:
            self.send_message(
                "<b>Bot baslatildi!</b>\n\n"
                f"Coin sayisi: {len(settings.symbols)}\n"
                f"Tarama araligi: {settings.check_interval}s\n"
                f"Pozisyon boyutu: ${settings.position_size_usd}"
            )
        else:
            self.send_message("Bot baslatilamadi! API baglantisi kontrol edin.")

    def cmd_stop(self, bot_instance):
        if not bot_instance or not bot_instance.running:
            self.send_message("Bot zaten durdurulmus!")
            return

        from src.main import stop_bot
        stop_bot()
        self.send_message("Bot durduruldu!")

    def cmd_status(self, bot_instance):
        if not bot_instance:
            self.send_message("Bot还不 calismiyor. /start ile baslatin.")
            return

        status = "CALISIYOR" if bot_instance.running else "DURDURULDU"
        if bot_instance.paused:
            status = "DURAKLATILDI"

        text = (
            f"<b>Durum:</b> {status}\n"
            f"<b>Tarama:</b> {bot_instance.total_scans}\n"
            f"<b>Sinyal:</b> {bot_instance.signals_sent}\n"
            f"<b>Son tarama:</b> {bot_instance.last_scan_time or '-'}\n"
            f"<b>Coin:</b> {len(settings.symbols)}"
        )
        self.send_message(text)

    def cmd_signals(self, bot_instance):
        if not bot_instance or not bot_instance.last_signals:
            self.send_message("Henuz sinyal yok.")
            return

        text = "<b>Son Sinyaller:</b>\n\n"
        for coin, sig in list(bot_instance.last_signals.items())[-10:]:
            emoji = "BUY" if sig.action == "BUY" else "SELL"
            text += f"<b>{coin}</b> - {emoji} (${sig.price:.4f}) - Guven: {sig.confidence:.0%}\n"
        self.send_message(text)

    def cmd_scan(self, bot_instance):
        if not bot_instance:
            self.send_message("Once /start ile botu baslatin.")
            return

        self.send_message("Tarama baslatildi... Lutfen bekleyin.")
        from src.main import CryptoBot
        if not bot_instance.running:
            import threading
            bot_instance.running = True
            t = threading.Thread(target=bot_instance.run_iteration, daemon=True)
            t.start()

    def cmd_help(self, bot_instance):
        self.send_message(
            "<b>Komutlar:</b>\n\n"
            "/start - Botu baslat\n"
            "/stop - Botu durdur\n"
            "/status - Durum goster\n"
            "/signals - Son sinyalleri goster\n"
            "/scan - Hemen tarama yap\n"
            "/help - Bu mesaji goster"
        )


telegram_bot_instance = None


def start_telegram_bot(bot_instance=None):
    global telegram_bot_instance
    telegram_bot_instance = TelegramBot(settings.telegram_bot_token, settings.telegram_chat_id)
    telegram_bot_instance.send_message("Bot hazir! Komutlar icin /help yazin.")
    return telegram_bot_instance
