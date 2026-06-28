import time
import threading
from datetime import datetime
from src.config import settings
from src.trader import trader
from src.analyzer import analyzer, Memory
from src.telegram import tg


class Bot:
    def __init__(self):
        self.running = False
        self.paused = False
        self.total_scans = 0
        self.signals_sent = 0
        self.last_scan = None
        self.last_signals = {}
        self.scan_results = []
        self.memory = Memory()
        self._lock = threading.Lock()
        self._pending_buys = {}
        self._buy_counter = 0

    def start(self):
        if self.running:
            return False
        self.running = True
        self.paused = False
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def stop(self):
        self.running = False
        return True

    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def _loop(self):
        while self.running:
            if not self.paused:
                self.scan()
            time.sleep(settings.check_interval)

    def scan(self):
        self.total_scans += 1
        self.last_scan = datetime.now().strftime('%H:%M:%S')
        self.scan_results = []

        for sym in settings.symbols:
            if not self.running:
                return
            try:
                df = trader.get_bars(sym, 60)
                if df.empty:
                    self.scan_results.append({
                        "symbol": sym, "action": "HOLD", "confidence": 0,
                        "price": 0, "rsi": 0, "volume_ratio": 0, "reason": "Veri yok"
                    })
                    continue

                ind = analyzer.analyze(df)
                if not ind:
                    self.scan_results.append({
                        "symbol": sym, "action": "HOLD", "confidence": 0,
                        "price": 0, "rsi": 0, "volume_ratio": 0, "reason": "Yetersiz veri"
                    })
                    continue

                action, confidence, reason = analyzer.score(ind, self.memory, sym)

                self.scan_results.append({
                    "symbol": sym, "action": action, "confidence": confidence,
                    "price": ind["price"], "rsi": ind["rsi"],
                    "volume_ratio": ind["vol_ratio"], "reason": reason
                })

                if action in ["BUY", "SELL"] and confidence >= settings.min_confidence:
                    prev = self.last_signals.get(sym)
                    if prev is None or action != prev["action"] or confidence > 0.7:
                        self.last_signals[sym] = {
                            "action": action, "confidence": confidence,
                            "price": ind["price"], "reason": reason,
                            "rsi": ind["rsi"], "time": self.last_scan
                        }
                        self._send_signal(sym, action, confidence, ind["price"], reason, ind)

            except Exception as e:
                self.scan_results.append({
                    "symbol": sym, "action": "HOLD", "confidence": 0,
                    "price": 0, "rsi": 0, "volume_ratio": 0, "reason": str(e)[:50]
                })

        self._check_ai_alerts()

    def _send_signal(self, symbol, action, confidence, price, reason, indicators):
        self.signals_sent += 1

        if action == "BUY":
            pos = trader.get_position(symbol)
            entry = pos["avg_entry_price"] if pos else 0
            pnl = pos["unrealized_pl"] if pos else 0

            self._buy_counter += 1
            self._pending_buys[self._buy_counter] = {
                "symbol": symbol, "action": action,
                "confidence": confidence, "price": price,
                "reason": reason, "indicators": indicators,
                "time": datetime.now().isoformat()
            }
            trade_id = self._buy_counter

            self.memory.record_signal(symbol, action, confidence, price, indicators, reason)
            tg.send_buy_signal(symbol, confidence, price, reason, trade_id)

        elif action == "SELL":
            pos = trader.get_position(symbol)
            if pos:
                entry = pos["avg_entry_price"]
                pnl = pos["unrealized_pl"]
                trade_id = self._buy_counter
                self._pending_buys[trade_id] = {
                    "symbol": symbol, "action": action,
                    "confidence": confidence, "price": price,
                    "reason": reason, "indicators": indicators,
                    "time": datetime.now().isoformat()
                }
                tg.send_sell_signal(symbol, confidence, price, reason, trade_id, entry, pnl)

    def _check_ai_alerts(self):
        for sym in settings.symbols:
            avoid, reason = self.memory.should_avoid(sym)
            if avoid:
                tg.send_ai_alert(sym, "down", reason)

    def get_status(self):
        try:
            acc = trader.get_account()
            positions = trader.get_positions()
            return {
                "running": self.running,
                "paused": self.paused,
                "total_scans": self.total_scans,
                "signals_sent": self.signals_sent,
                "last_scan": self.last_scan,
                "symbols": settings.symbols,
                "position_size": settings.position_size_usd,
                "stop_loss": settings.stop_loss_pct,
                "take_profit": settings.take_profit_pct,
                "balance": acc,
                "positions": positions,
                "scan_results": self.scan_results,
                "last_signals": self.last_signals,
            }
        except Exception as e:
            return {
                "running": self.running,
                "paused": self.paused,
                "total_scans": self.total_scans,
                "signals_sent": self.signals_sent,
                "last_scan": self.last_scan,
                "error": str(e)
            }

    def get_memory_data(self):
        return {
            "stats": self.memory.get_win_rate(),
            "recent": self.memory.get_recent(10)
        }


bot = Bot()


def setup_telegram():
    tg.on_start(lambda: bot.start())
    tg.on_stop(lambda: bot.stop())
    tg.on_scan(lambda: bot.scan())
    tg.on_status(lambda: bot.get_status())
    tg.on_signals(lambda: bot.last_signals)
    tg.on_memory(lambda: bot.get_memory_data())
    tg.start_polling()
