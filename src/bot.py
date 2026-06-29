import time
import threading
import requests
from datetime import datetime, date
from src.config import settings
from src.trader import trader
from src.executor import executor
from src.telegram import tg
from src.deepseek_ai import ai
from src.analyzer import Memory


class Bot:
    def __init__(self):
        self.running = False
        self.paused = False
        self.auto_trade = False
        self.total_scans = 0
        self.signals_sent = 0
        self.last_scan = None
        self.last_decision = None
        self.memory = Memory()
        self.daily_pnl = 0
        self.today = date.today()
        self.scan_results = []
        self.last_signals = {}
        self._current_trade_id = None

    def start(self):
        if self.running:
            return False
        self.running = True
        self.paused = False
        threading.Thread(target=self._main_loop, daemon=True).start()
        return True

    def stop(self):
        self.running = False
        return True

    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def _main_loop(self):
        tg.send(
            f"<b>BTC BOT BASLATILDI</b>\n\n"
            f"Miktar: ${settings.position_size_usd:.0f}\n"
            f"Hedef: ${settings.daily_profit_target:.0f}/gun\n"
            f"Stop-loss: %{settings.stop_loss_pct:.0f}\n"
            f"Mod: <b>{'OTO' if self.auto_trade else 'ONAYLI'}</b>\n"
            f"Islem: <b>{settings.executor_mode.upper()}</b>\n"
            f"Her {settings.check_interval}s'de bir tarayacak..."
        )
        time.sleep(2)
        while self.running:
            if not self.paused:
                self._reset_daily()
                try:
                    self.scan()
                except Exception as e:
                    print(f"[BOT] Hata: {e}")
            time.sleep(settings.check_interval)

    def _reset_daily(self):
        if date.today() != self.today:
            self.daily_pnl = 0
            self.today = date.today()

    def scan(self):
        self.total_scans += 1
        self.last_scan = datetime.now().strftime('%H:%M:%S')
        print(f"\n[SCAN #{self.total_scans}] {self.last_scan}")

        if self._check_stop_loss():
            return

        df = trader.get_bars(100)
        if df.empty:
            print("  Veri yok")
            return

        price = trader.get_price()
        decision = ai.analyze(df)
        self.last_decision = decision
        action = decision.get("action", "HOLD")
        confidence = decision.get("confidence", 0)
        reason = decision.get("reason", "")

        print(f"  BTC ${price:,.2f} -> {action} ({confidence:.0%}) {reason[:60]}")
        print(f"  Mod: {settings.executor_mode.upper()}")

        entry = {
            "symbol": "BTC/USDT",
            "action": action,
            "confidence": confidence,
            "price": price,
            "rsi": decision.get("rsi", 50),
            "reason": reason
        }
        self.scan_results = [entry]
        self.last_signals = {action: {"action": action, "price": price, "confidence": confidence, "reason": reason}}

        self._check_daily_profit()

        has_pos = executor.get_position() is not None

        if action == "BUY" and confidence >= 0.4 and not has_pos:
            self.signals_sent += 1
            if self.auto_trade:
                self._exec_buy(price, decision)
            else:
                self._buy_counter = getattr(self, '_buy_counter', 0) + 1
                tg.send_buy_signal("BTC", confidence, price, reason, self._buy_counter)

        elif action == "SELL" and confidence >= 0.4 and has_pos:
            self.signals_sent += 1
            if self.auto_trade:
                self._exec_sell(reason=f"AI: {reason}", confidence=confidence)
            else:
                self._sell_counter = getattr(self, '_sell_counter', 0) + 1
                pos = executor.get_position()
                pnl = pos['unrealized_pl'] if pos else 0
                entry_price = pos['avg_entry_price'] if pos else 0
                tg.send_sell_signal("BTC", confidence, price, reason, self._sell_counter, entry_price, pnl)

    def _check_stop_loss(self):
        pos = executor.get_position()
        if not pos or settings.last_entry_price <= 0:
            return False
        price = trader.get_price()
        loss_pct = (price - settings.last_entry_price) / settings.last_entry_price * 100
        if loss_pct <= -settings.stop_loss_pct:
            print(f"[STOP-LOSS] Kayip: {loss_pct:.1f}% - Satiliyor...")
            try:
                result = executor.sell()
                if result:
                    self.daily_pnl += result['pl']
                    self._close_memory_trade(result['pl'])
                    tg.send(
                        f"<b>STOP-LOSS TETIKLENDI</b>\n\n"
                        f"Giris: <code>${settings.last_entry_price:,.2f}</code>\n"
                        f"Cikis: <code>${price:,.2f}</code>\n"
                        f"Kayip: <b>{loss_pct:.1f}%</b>\n"
                        f"K/Z: <code>${result['pl']:+,.2f}</code>")
                    return True
            except Exception as e:
                tg.send(f"<b>STOP-LOSS HATASI</b>\n<code>{str(e)[:100]}</code>")
        return False

    def _check_daily_profit(self):
        if self.daily_pnl >= settings.daily_profit_target:
            pos = executor.get_position()
            if pos:
                tg.send(f"<b>GUNLUK HEDEF</b>\n\nKar: ${self.daily_pnl:.2f}\nHedef: ${settings.daily_profit_target:.0f}\nSatiliyor...")
                try:
                    result = executor.sell_all()
                    if result:
                        self._close_memory_trade(self.daily_pnl)
                except Exception as e:
                    tg.send(f"<b>SATIS HATASI</b>\n<code>{str(e)[:100]}</code>")
            self.paused = True

    def _exec_buy(self, price, decision=None):
        try:
            result = executor.buy()
            trade_id = self.memory.record_signal("BTC/USDT", "BUY",
                decision.get('confidence', 0) if decision else 0, price,
                decision or {}, decision.get('reason', '') if decision else '')
            self._current_trade_id = trade_id
            prefix = "SIMULASYON " if settings.executor_mode == "dry_run" else ""
            tg.send(
                f"<b>{prefix}ALIS</b>  <code>BTC</code>\n"
                f"Miktar: <code>{result['qty']:.6f}</code>\n"
                f"Giris: <code>${result['price']:,.2f}</code>"
                f"{'  (dry-run)' if settings.executor_mode == 'dry_run' else ''}")
        except Exception as e:
            tg.send(f"<b>ALIS HATASI</b>\n<code>{str(e)[:200]}</code>")

    def _exec_sell(self, reason="", confidence=0):
        try:
            result = executor.sell()
            if result:
                if self._current_trade_id:
                    self.memory.close_trade(self._current_trade_id, result['pl'])
                    self._current_trade_id = None
                self.daily_pnl += result['pl']
                prefix = "SIMULASYON " if settings.executor_mode == "dry_run" else ""
                txt = (
                    f"<b>{prefix}SATIS</b>  <code>BTC</code>\n"
                    f"K/Z: <code>${result['pl']:+,.2f}</code>\n"
                    f"Gunluk: ${self.daily_pnl:+,.2f}"
                    f"{'  (dry-run)' if settings.executor_mode == 'dry_run' else ''}")
                if reason:
                    txt += f"\n<i>{reason[:80]}</i>"
                tg.send(txt)
        except Exception as e:
            tg.send(f"<b>SATIS HATASI</b>\n<code>{str(e)[:200]}</code>")

    def _close_memory_trade(self, pnl):
        if self._current_trade_id:
            self.memory.close_trade(self._current_trade_id, pnl)
            self._current_trade_id = None

    def _has_position(self):
        return executor.get_position() is not None

    def get_status(self):
        try:
            acc = executor.get_account()
            pos = executor.get_position()
            return {
                "running": self.running,
                "paused": self.paused,
                "auto_trade": self.auto_trade,
                "total_scans": self.total_scans,
                "signals_sent": self.signals_sent,
                "last_scan": self.last_scan,
                "symbol": "BTC/USDT",
                "position_size": settings.position_size_usd,
                "daily_target": settings.daily_profit_target,
                "daily_pnl": self.daily_pnl,
                "balance": acc,
                "position": pos,
                "last_decision": self.last_decision,
                "scan_results": self.scan_results,
                "last_signals": self.last_signals,
                "executor_mode": settings.executor_mode,
                "stop_loss_pct": settings.stop_loss_pct,
            }
        except Exception as e:
            return {
                "running": self.running,
                "paused": self.paused,
                "auto_trade": self.auto_trade,
                "total_scans": self.total_scans,
                "signals_sent": self.signals_sent,
                "last_scan": self.last_scan,
                "error": str(e),
            }

    def get_memory_data(self):
        stats = self.memory.get_win_rate()
        return {
            "stats": stats,
            "recent": self.memory.get_recent(10),
            "last_decision": self.last_decision,
        }


bot = Bot()


def setup_telegram():
    tg.on_start(lambda: bot.start())
    tg.on_stop(lambda: bot.stop())
    tg.on_scan(lambda: bot.scan())
    tg.on_status(lambda: bot.get_status())
    tg.on_memory(lambda: bot.get_memory_data())
    tg.on_oto(lambda: _toggle_auto(True))
    tg.on_manuel(lambda: _toggle_auto(False))
    tg.start_polling()


def _toggle_auto(enabled):
    bot.auto_trade = enabled
    mod = "OTO" if enabled else "ONAYLI"
    tg.send(f"<b>MOD</b>\n\nIslem modu: <b>{mod}</b>\n"
            f"Islem: <b>{settings.executor_mode.upper()}</b>")
