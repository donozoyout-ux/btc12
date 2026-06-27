import time
import signal
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
        self.last_scan_time = None
        self.total_scans = 0
        self.signals_sent = 0

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        print("\n[STOP] Shutdown signal received...")
        self.running = False

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
            df = self.client.get_bars(symbol=sym, limit=100)
            if df.empty:
                result["reason"] = "No data"
                return result

            sig = self.strategy.analyze(df)
            if not sig:
                result["reason"] = "Insufficient data"
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

            # Print to console
            action_label = {"BUY": "[BUY]", "SELL": "[SELL]"}.get(sig.action, "")
            if action_label:
                print(f"  {action_label} {sym:12s} ${sig.price:,.4f} RSI:{sig.rsi:.1f} Vol:{sig.volume_ratio:.1f}x ({sig.confidence:.0%})")

            # Notify if actionable
            if sig.action != "HOLD" and sig.confidence >= 0.4:
                prev = self.last_signals.get(sym)
                if prev is None or sig.action != prev.action or sig.confidence > 0.7:
                    pos = self.client.get_position(sym)
                    info = pos if pos else {"symbol": sym}
                    self.telegram.send_signal(sig, info)
                    self.last_signals[sym] = sig
                    self.signals_sent += 1

            # Execute trades
            position = self.client.get_position(sym)
            has_position = position is not None

            if sig.action == "BUY" and not has_position and sig.confidence >= 0.6:
                self.execute_buy(sym, sig)
            elif sig.action == "SELL" and has_position and sig.confidence >= 0.6:
                self.execute_sell(sym, sig)

        except Exception as e:
            result["reason"] = f"Error: {e}"

        return result

    def run_iteration(self):
        self.total_scans += 1
        self.scan_results = []
        self.last_scan_time = datetime.now().strftime('%H:%M:%S')

        print(f"\n{'='*60}")
        print(f"[*] Scan #{self.total_scans} at {self.last_scan_time} | {len(settings.symbols)} symbols")

        for i, sym in enumerate(settings.symbols, 1):
            if not self.running:
                break
            result = self.scan_symbol(sym)
            self.scan_results.append(result)
            time.sleep(0.3)

        actionable = [r for r in self.scan_results if r["action"] != "HOLD"]
        print(f"[*] Done | Actionable: {len(actionable)} | Signals sent: {self.signals_sent}")

    def execute_buy(self, sym: str, sig: Signal):
        print(f"  [BUY] {sym} at ${sig.price:,.4f}")
        try:
            price = self.client.get_latest_price(sym)
            qty = self.client.calculate_qty(settings.position_size_usd, price)

            order = self.client.place_market_order(OrderSide.BUY, qty, sym)
            print(f"  [OK] Buy: {qty} {sym} @ ${price:,.4f}")

            stop_price = price * (1 - settings.stop_loss_pct)
            self.client.place_stop_loss(qty, stop_price, sym)

            tp_price = price * (1 + settings.take_profit_pct)
            self.client.place_limit_order(OrderSide.SELL, qty, tp_price, sym)

            self.telegram.send_order(order, "PLACED")

        except Exception as e:
            print(f"  [ERROR] Buy failed: {e}")
            self.telegram.send_error(f"{sym} buy failed: {e}")

    def execute_sell(self, sym: str, sig: Signal):
        print(f"  [SELL] {sym} at ${sig.price:,.4f}")
        try:
            position = self.client.get_position(sym)
            qty = position["qty"]
            self.client.cancel_all_orders()
            order = self.client.place_market_order(OrderSide.SELL, qty, sym)
            print(f"  [OK] Sell: {qty} {sym}")
            self.telegram.send_order(order, "PLACED")
        except Exception as e:
            print(f"  [ERROR] Sell failed: {e}")
            self.telegram.send_error(f"{sym} sell failed: {e}")

    def run(self):
        print("[START] Crypto Scanner Bot")
        print(f"[*] {len(settings.symbols)} coins | ${settings.position_size_usd}/trade | Every {settings.check_interval}s")

        if not self.check_connection():
            return

        self.telegram.send_status(f"Bot started - {len(settings.symbols)} coins")

        self.running = True
        while self.running:
            try:
                if not self.paused:
                    self.run_iteration()
                else:
                    print("[PAUSED] Waiting...")
            except Exception as e:
                print(f"[ERROR] {e}")
                self.telegram.send_error(str(e))

            if self.running:
                for _ in range(settings.check_interval):
                    if not self.running:
                        break
                    time.sleep(1)

        self.telegram.send_status("Bot stopped")
        print("[DONE] Bot stopped")


bot = CryptoBot()


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
        "scan_results": bot.scan_results[-20:],
        "last_signals": {k: {"action": v.action, "confidence": v.confidence, "price": v.price} for k, v in bot.last_signals.items()}
    }


if __name__ == "__main__":
    bot.run()
