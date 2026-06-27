import requests
from src.config import settings


class TelegramNotifier:
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            print(f"Telegram error: {e}")
            return False

    def send_signal(self, signal, position_info: dict = None) -> bool:
        symbol = position_info.get("symbol", "UNKNOWN") if position_info else "UNKNOWN"

        if signal.action == "BUY":
            action_text = "ALIS"
            emoji = "BUY"
        elif signal.action == "SELL":
            action_text = "SATIS"
            emoji = "SELL"
        else:
            action_text = "BEKLE"
            emoji = "HOLD"

        text = (
            f"<b>[{emoji}] {symbol} - {action_text}</b> (Guven: {signal.confidence:.0%})\n\n"
            f"<b>Fiyat:</b> ${signal.price:,.4f}\n"
            f"<b>RSI:</b> {signal.rsi:.1f}\n"
            f"<b>BB:</b> ${signal.bb_lower:,.4f} - ${signal.bb_middle:,.4f} - ${signal.bb_upper:,.4f}\n"
            f"<b>Hacim:</b> {signal.volume_ratio:.1f}x ort\n"
            f"<b>Degisim:</b> {signal.price_change_pct*100:+.2f}%\n\n"
            f"<i>{signal.reason}</i>"
        )

        if position_info and position_info.get("qty", 0) > 0:
            text += (
                f"\n\n<b>Pozisyon:</b> {position_info.get('qty', 0):.6f} {symbol}"
                f"\n<b>Giris:</b> ${position_info.get('avg_entry_price', 0):,.4f}"
                f"\n<b>K/Z:</b> ${position_info.get('unrealized_pl', 0):+,.4f}"
            )

        return self.send_message(text)

    def send_order(self, order: dict, action: str) -> bool:
        side = order.get("side", "").upper()
        symbol = order.get("symbol", "UNKNOWN")
        status = order.get("status", "unknown")

        if status == "filled":
            durum = "TAMAMLANDI"
            emoji = "DONE"
        else:
            durum = "BEKLEMEDE"
            emoji = "PENDING"

        if side == "BUY":
            islem = "ALIS"
        else:
            islem = "SATIS"

        text = (
            f"<b>[{emoji}] {symbol} - {islem}</b>\n\n"
            f"<b>Miktar:</b> {order.get('qty', 0):.6f}\n"
            f"<b>Fiyat:</b> ${order.get('filled_avg_price', order.get('limit_price', 0)):,.4f}\n"
            f"<b>Durum:</b> {durum}"
        )
        return self.send_message(text)

    def send_error(self, error: str) -> bool:
        text = f"<b>[HATA]</b>\n\n<code>{error}</code>"
        return self.send_message(text)

    def send_status(self, message: str) -> bool:
        text = f"<b>[DURUM]</b>\n\n{message}"
        return self.send_message(text)