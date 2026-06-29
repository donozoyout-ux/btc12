import requests
import time
import threading
from src.config import settings


class TelegramBot:
    def __init__(self):
        self.base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self.chat_id = settings.telegram_chat_id
        self.last_update_id = 0
        self.running = False
        self._on_start = None
        self._on_stop = None
        self._on_scan = None
        self._on_status = None
        self._on_buy_onay = None
        self._on_sell_onay = None
        self._on_oto = None
        self._on_manuel = None
        self._on_miktar = None
        self._on_artir = None
        self._on_azalt = None

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
            r = requests.get(
                f"{self.base}/getUpdates",
                params={"offset": self.last_update_id + 1, "timeout": 3},
                timeout=10
            )
            return r.json().get("result", []) if r.status_code == 200 else []
        except:
            return []

    def handle(self, text, chat_id):
        if str(chat_id) != str(self.chat_id):
            return
        low = text.strip().lower().lstrip("/")

        if low in ["onay", "evet", "yap", "1"]:
            if self._on_buy_onay:
                self._on_buy_onay()
            return

        if low in ["sat", "satis"]:
            if self._on_sell_onay:
                self._on_sell_onay()
            return

        if low in ["hayir", "yapma", "iptal", "0"]:
            self.send("Islem iptal edildi.")
            return

        if low == "start":
            if self._on_start:
                self._on_start()
            return

        if low == "stop":
            if self._on_stop:
                self._on_stop()
            return

        if low in ["status", "durum"]:
            if self._on_status:
                self._on_status()
            return

        if low == "scan":
            if self._on_scan:
                self._on_scan()
            return

        if low == "oto":
            if self._on_oto:
                self._on_oto()
            return

        if low in ["manuel", "onayli"]:
            if self._on_manuel:
                self._on_manuel()
            return

        parts = low.split()
        if parts[0] == "miktar" and len(parts) == 1:
            if self._on_miktar:
                self._on_miktar(None)
            return
        if parts[0] == "miktar" and len(parts) == 2:
            try:
                val = int(parts[1])
                if self._on_miktar:
                    self._on_miktar(val)
            except:
                self.send("Gecerli bir sayi girin. Ornek: <code>/miktar 100</code>")
            return
        if parts[0] in ("artir", "arttir") and len(parts) == 2:
            try:
                val = int(parts[1])
                if self._on_artir:
                    self._on_artir(val)
            except:
                self.send("Gecerli bir sayi girin. Ornek: <code>/artir 50</code>")
            return
        if parts[0] == "azalt" and len(parts) == 2:
            try:
                val = int(parts[1])
                if self._on_azalt:
                    self._on_azalt(val)
            except:
                self.send("Gecerli bir sayi girin. Ornek: <code>/azalt 25</code>")
            return

    def send_buy_signal(self, fiyat, confidence, sl, tp, reason):
        msg = (
            f"\U0001f7e2 <b>BTC ALIS SINYALI</b>\n\n"
            f"Fiyat: <code>${fiyat:,.2f}</code>\n"
            f"Guven: <b>%{confidence:.0f}</b>\n"
            f"SL: <code>${sl:,.2f}</code> | TP: <code>${tp:,.2f}</code>\n\n"
            f"<i>{reason}</i>\n\n"
            f"<code>/onay</code> - Alisi onayla\n"
            f"<code>/iptal</code> - Reddet"
        )
        self.send(msg)

    def send_sell_signal(self, fiyat, giris, kar_zarar, yuzde, reason):
        emoji = "\U0001f7e2" if kar_zarar > 0 else "\U0001f534"
        msg = (
            f"\U0001f534 <b>BTC SATIS SINYALI</b>\n\n"
            f"Giris: <code>${giris:,.2f}</code>\n"
            f"Simdi: <code>${fiyat:,.2f}</code>\n"
            f"K/Z: {emoji} <b>${kar_zarar:+,.2f}</b> (%{yuzde:+.2f})\n\n"
            f"<i>{reason}</i>\n\n"
            f"<code>/sat</code> - Satisi onayla\n"
            f"<code>/iptal</code> - Reddet"
        )
        self.send(msg)

    def send_islem_sonucu(self, tur, fiyat, miktar, kar_zarar=None):
        if tur == "BUY":
            msg = (
                f"\U0001f7e2 <b>ALIS GERCEKLESTI</b>\n\n"
                f"Miktar: <code>{miktar:.6f} BTC</code>\n"
                f"Fiyat: <code>${fiyat:,.2f}</code>"
            )
        else:
            msg = (
                f"\U0001f534 <b>SATIS GERCEKLESTI</b>\n\n"
                f"Miktar: <code>{miktar:.6f} BTC</code>\n"
                f"Fiyat: <code>${fiyat:,.2f}</code>\n"
                f"K/Z: <code>${kar_zarar:+,.2f}</code>" if kar_zarar else ""
            )
        self.send(msg)

    def send_durum(self, data):
        if not data:
            self.send("Bot calismiyor.")
            return

        durum = "AKTIF" if data.get("running") else "DURDU"
        mod = "OTO" if data.get("auto_trade") else "ONAYLI"
        msg = (
            f"<b>DURUM</b>\n\n"
            f"Bot: <b>{durum}</b>\n"
            f"Mod: <b>{mod}</b>\n"
            f"Portfoy: <code>${data.get('portfolio_value', 0):,.2f}</code>\n"
            f"Nakit: <code>${data.get('cash', 0):,.2f}</code>\n"
            f"Pozisyon: {data.get('pozisyon_durumu', 'Yok')}\n"
            f"Tarama: {data.get('total_scans', 0)}"
        )
        if data.get("kar_zarar"):
            msg += f"\nAcik K/Z: <code>${data['kar_zarar']:+,.2f}</code>"
        self.send(msg)

    def poll(self):
        print("[TG] Telegram dinleniyor...")
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
            except:
                pass
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
    def on_buy_onay(self, fn):
        self._on_buy_onay = fn
    def on_sell_onay(self, fn):
        self._on_sell_onay = fn
    def on_oto(self, fn):
        self._on_oto = fn
    def on_manuel(self, fn):
        self._on_manuel = fn


    def on_miktar(self, fn):
        self._on_miktar = fn
    def on_artir(self, fn):
        self._on_artir = fn
    def on_azalt(self, fn):
        self._on_azalt = fn


tg = TelegramBot()
