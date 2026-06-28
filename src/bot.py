import time
import threading
import requests
from datetime import datetime
from src.config import settings
from src.trader import trader
from src.analyzer import analyzer, Memory
from src.telegram import tg
from src.ai_engine import ai_engine


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
        self._last_indicators = {}

    def start(self):
        if self.running:
            return False
        self.running = True
        self.paused = False
        threading.Thread(target=self._main_loop, daemon=True).start()
        threading.Thread(target=self._keep_alive, daemon=True).start()
        return True

    def stop(self):
        self.running = False
        return True

    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def _main_loop(self):
        tg.send("<b>TARAMA BASLATILDI</b>\n\nBTC ve ETH taraniyor...")
        time.sleep(2)
        self.scan()
        while self.running:
            if not self.paused:
                self.scan()
            time.sleep(settings.check_interval)

    def _keep_alive(self):
        while self.running:
            time.sleep(600)
            try:
                port = 10000
                requests.get(f"http://127.0.0.1:{port}/", timeout=5)
            except:
                pass

    def scan(self):
        self.total_scans += 1
        self.last_scan = datetime.now().strftime('%H:%M:%S')
        self.scan_results = []

        print(f"\n[SCAN #{self.total_scans}] {self.last_scan}")

        for sym in settings.symbols:
            if not self.running:
                return
            try:
                df = trader.get_bars(sym, 60)
                if df.empty:
                    print(f"  [{sym}] Veri yok")
                    self.scan_results.append({
                        "symbol": sym, "action": "HOLD", "confidence": 0,
                        "price": 0, "rsi": 0, "volume_ratio": 0, "reason": "Veri yok"
                    })
                    continue

                ind = analyzer.analyze(df)
                if not ind:
                    print(f"  [{sym}] Yetersiz veri")
                    self.scan_results.append({
                        "symbol": sym, "action": "HOLD", "confidence": 0,
                        "price": 0, "rsi": 0, "volume_ratio": 0, "reason": "Yetersiz veri"
                    })
                    continue

                self._last_indicators[sym] = ind
                action, confidence, reason = analyzer.score(ind, self.memory, sym)

                print(f"  [{sym}] ${ind['price']:,.2f} RSI:{ind['rsi']:.1f} -> {action} ({confidence:.0%}) {reason[:40]}")

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
                print(f"  [{sym}] HATA: {e}")
                self.scan_results.append({
                    "symbol": sym, "action": "HOLD", "confidence": 0,
                    "price": 0, "rsi": 0, "volume_ratio": 0, "reason": str(e)[:50]
                })

        if self.total_scans == 1 or self.total_scans % 5 == 0:
            self._send_scan_summary()

        self._check_ai_alerts()

    def _send_scan_summary(self):
        if not self.scan_results:
            return
        msg = f"<b>TARAMA #{self.total_scans}</b>  {self.last_scan}\n\n"
        for r in self.scan_results:
            emoji = "BUY" if r["action"] == "BUY" else "SELL" if r["action"] == "SELL" else "---"
            msg += f"<code>{r['symbol']:8s}</code> ${r['price']:>10,.2f}  RSI:{r['rsi']:5.1f}  <b>{emoji}</b>\n"
        tg.send(msg, silent=True)

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
                "time": datetime.now().isoformat(), "recorded": False
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
                    "time": datetime.now().isoformat(), "recorded": False
                }

                if entry > 0:
                    outcome, pnl_usd = self.record_trade_result(symbol, entry, price, indicators)
                    tg.send_ai_alert(symbol, "down" if outcome == "LOSS" else "up",
                                     f"Islem kapatildi: {outcome} (${pnl_usd:+,.2f})")

                tg.send_sell_signal(symbol, confidence, price, reason, trade_id, entry, pnl)

    def record_trade_result(self, symbol, entry_price, exit_price, indicators):
        pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
        outcome = "WIN" if pnl_pct > 0 else "LOSS" if pnl_pct < 0 else "BREAKEVEN"
        pnl_usd = pnl_pct * settings.position_size_usd

        ai_engine.record_outcome(
            symbol, "BUY", 0, entry_price, indicators, outcome, pnl_usd
        )
        self.memory.record_signal(
            symbol, "BUY", 0, entry_price, indicators, f"Sonuc: {outcome}"
        )
        self.memory.close_trade(len(self.memory.trades), pnl_usd)

        return outcome, pnl_usd

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
        memory_stats = self.memory.get_win_rate()
        ai_stats = ai_engine.get_stats()
        return {
            "stats": memory_stats,
            "recent": self.memory.get_recent(10),
            "ai": ai_stats
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
