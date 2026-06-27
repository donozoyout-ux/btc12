import time
import sys
import json
import threading
from datetime import datetime
from typing import Optional
sys.path.insert(0, '.')
from src.config import settings
from src.alpaca_client import AlpacaClient
from src.strategy import Strategy, Signal
from src.telegram_notifier import TelegramNotifier
from alpaca.trading.enums import OrderSide


class CryptoBot:
    def __init__(self):
        self.client = AlpacaClient()
        self.strategy = Strategy()
        self.telegram = TelegramNotifier()
        self.running = False
        self.paused = False
        self.last_signals = {}
        self.scan_results = []
        self.pending_notifications = []
        self.last_scan_time = None
        self.total_scans = 0
        self.signals_sent = 0

    def check_connection(self) -> bool:
        try:
            account = self.client.get_account()
            print(f"[OK] Connected | Balance: ${float(account.portfolio_value):,.2f}")
            return True
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            return False

    def scan_symbol(self, sym: str) -> dict:
        result = {"symbol": sym, "action": "HOLD", "confidence": 0, "price": 0, "reason": ""}
        try:
            df = self.client.get_bars(symbol=sym, limit=50)
            if df.empty:
                result["reason"] = "Veri yok"
                return result

            sig = self.strategy.analyze(df)
            if not sig:
                result["reason"] = "Yetersiz veri"
                return result

            result = {
                "symbol": sym,
                "action": sig.action,
                "confidence": sig.confidence,
                "price": sig.price,
                "rsi": sig.rsi,
                "volume_ratio": sig.volume_ratio,
                "price_change_pct": sig.price_change_pct,
                "reason": sig.reason
            }

            action_label = {"BUY": "[ALIS]", "SELL": "[SATIS]"}.get(sig.action, "")
            if action_label:
                print(f"  {action_label} {sym:12s} ${sig.price:,.4f} RSI:{sig.rsi:.1f} ({sig.confidence:.0%})")

            if sig.action != "HOLD" and sig.confidence >= 0.4:
                prev = self.last_signals.get(sym)
                if prev is None or sig.action != prev.action or sig.confidence > 0.7:
                    self.pending_notifications.append((sym, sig))
                    self.last_signals[sym] = sig
                    self.signals_sent += 1

            position = self.client.get_position(sym)
            has_position = position is not None

            if sig.action == "BUY" and not has_position and sig.confidence >= 0.6:
                self.execute_buy(sym, sig)
            elif sig.action == "SELL" and has_position and sig.confidence >= 0.6:
                self.execute_sell(sym, sig)

        except Exception as e:
            result["reason"] = f"Hata: {e}"

        return result

    def run_iteration(self):
        self.total_scans += 1
        self.scan_results = []
        self.pending_notifications = []
        self.last_scan_time = datetime.now().strftime('%H:%M:%S')

        print(f"\n{'='*60}")
        print(f"[*] Tarama #{self.total_scans} | {self.last_scan_time} | {len(settings.symbols)} coin")

        for i, sym in enumerate(settings.symbols, 1):
            if not self.running:
                break
            result = self.scan_symbol(sym)
            self.scan_results.append(result)

        for sym, sig in self.pending_notifications:
            try:
                pos = self.client.get_position(sym)
                info = pos if pos else {"symbol": sym}
                self.telegram.send_signal(sig, info)
            except:
                pass

        actionable = [r for r in self.scan_results if r["action"] != "HOLD"]
        print(f"[*] Tamamlandi | Sinyal: {len(actionable)} | Toplam: {self.signals_sent}")

    def execute_buy(self, sym: str, sig: Signal):
        print(f"  [ALIS] {sym} ${sig.price:,.4f}")
        try:
            price = self.client.get_latest_price(sym)
            qty = self.client.calculate_qty(settings.position_size_usd, price)

            order = self.client.place_market_order(OrderSide.BUY, qty, sym)
            print(f"  [OK] Alis: {qty} {sym} @ ${price:,.4f}")

            stop_price = price * (1 - settings.stop_loss_pct)
            self.client.place_stop_loss(qty, stop_price, sym)

            tp_price = price * (1 + settings.take_profit_pct)
            self.client.place_limit_order(OrderSide.SELL, qty, tp_price, sym)

            self.telegram.send_order(order, "YERLESTIRILDI")

        except Exception as e:
            print(f"  [HATA] Alis basarisiz: {e}")
            self.telegram.send_error(f"{sym} alis basarisiz: {e}")

    def execute_sell(self, sym: str, sig: Signal):
        print(f"  [SATIS] {sym} ${sig.price:,.4f}")
        try:
            position = self.client.get_position(sym)
            qty = position["qty"]
            self.client.cancel_all_orders()
            order = self.client.place_market_order(OrderSide.SELL, qty, sym)
            print(f"  [OK] Satis: {qty} {sym}")
            self.telegram.send_order(order, "YERLESTIRILDI")
        except Exception as e:
            print(f"  [HATA] Satis basarisiz: {e}")
            self.telegram.send_error(f"{sym} satis basarisiz: {e}")

    def run(self):
        print("[BASLAT] Crypto Scanner Bot")
        print(f"[*] {len(settings.symbols)} coin | ${settings.position_size_usd}/islem | {settings.check_interval}s aralikla")

        self.running = True
        self.telegram.send_status(f"Bot baslatildi - {len(settings.symbols)} coin taraniyor")

        while self.running:
            try:
                if not self.paused:
                    self.run_iteration()
                else:
                    print("[DURAKLATILDI] Bekleniyor...")
            except Exception as e:
                print(f"[HATA] {e}")
                self.telegram.send_error(str(e))

            if self.running:
                for _ in range(settings.check_interval):
                    if not self.running:
                        break
                    time.sleep(1)

        self.telegram.send_status("Bot durduruldu")
        print("[DURDU] Bot durduruldu")


bot = CryptoBot()
telegram_bot_handler = None


def start_bot():
    global bot
    if not bot.running:
        bot = CryptoBot()
        thread = threading.Thread(target=bot.run, daemon=True)
        thread.start()
        return True
    return False


def stop_bot():
    global bot
    if bot.running:
        bot.running = False
        return True
    return False


def pause_bot():
    global bot
    bot.paused = not bot.paused
    return bot.paused


def get_status():
    global bot
    return {
        "running": bot.running,
        "paused": bot.paused,
        "total_scans": bot.total_scans,
        "signals_sent": bot.signals_sent,
        "last_scan_time": bot.last_scan_time,
        "symbols_count": len(settings.symbols),
        "scan_results": bot.scan_results,
        "last_signals": {k: {"action": v.action, "confidence": v.confidence, "price": v.price, "reason": v.reason} for k, v in bot.last_signals.items()}
    }


def poll_telegram():
    global telegram_bot_handler, bot
    from src.telegram_bot import TelegramBot
    telegram_bot_handler = TelegramBot(settings.telegram_bot_token, settings.telegram_chat_id)
    telegram_bot_handler.send_message("Bot hazir! Komutlar icin /help yazin.")
    while True:
        try:
            telegram_bot_handler.poll_commands(bot)
        except Exception as e:
            print(f"[TELEGRAM HATA] {e}")
        time.sleep(2)


if __name__ == "__main__":
    tg_thread = threading.Thread(target=poll_telegram, daemon=True)
    tg_thread.start()
    bot.run()
