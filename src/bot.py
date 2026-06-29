import time
import threading
import requests
from datetime import datetime
from src.config import settings
from src.trader import trader
from src.analyzer import analyzer, Memory
from src.telegram import tg
from src.ai_engine import ai_engine
from src.agents.ml_agent import ml_agent


class Bot:
    def __init__(self):
        self.running = False
        self.paused = False
        self.total_scans = 0
        self.signals_sent = 0
        self.last_scan = None
        self.last_signals = {}
        self.scan_results = []
        self.agent_results = {}
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
        tg.send(
            f"<b>TARAMA BASLATILDI</b>\n\n"
            f"Coin: BTC, ETH\n"
            f"Miktar: ${settings.position_size_usd:.0f}\n"
            f"6 AI Agent: Technical, Sentiment, Volume, Trend, Pattern, ML\n"
            f"Her {settings.check_interval}s'de bir tarayacak..."
        )
        time.sleep(2)
        try:
            self.scan()
        except Exception as e:
            print(f"[SCAN HATA] {e}")
            tg.send(f"<b>TARAMA HATASI</b>\n\n<code>{str(e)[:200]}</code>")
        while self.running:
            if not self.paused:
                try:
                    self.scan()
                except Exception as e:
                    print(f"[SCAN HATA] {e}")
            time.sleep(settings.check_interval)

    def _keep_alive(self):
        while self.running:
            time.sleep(600)
            try:
                requests.get("http://127.0.0.1:10000/api/keepalive", timeout=5)
            except:
                pass

    def scan(self):
        self.total_scans += 1
        self.last_scan = datetime.now().strftime('%H:%M:%S')
        new_results = []

        print(f"\n[SCAN #{self.total_scans}] {self.last_scan}")

        for sym in settings.symbols:
            if not self.running:
                return
            try:
                df = trader.get_bars(sym, 60)
                if df.empty:
                    print(f"  [{sym}] Veri yok")
                    new_results.append({
                        "symbol": sym, "action": "HOLD", "confidence": 0,
                        "price": 0, "rsi": 0, "volume_ratio": 0, "reason": "Veri yok"
                    })
                    continue

                result = analyzer.analyze(df)

                action = result["direction"]
                if action == "BUY":
                    action = "BUY"
                elif action == "SELL":
                    action = "SELL"
                else:
                    action = "HOLD"

                new_results.append({
                    "symbol": sym, "action": action, "confidence": result["confidence"],
                    "price": result["price"], "rsi": result["rsi"],
                    "volume_ratio": result["volume_ratio"],
                    "reason": "; ".join(result["reasons"][:3])
                })

                self.agent_results[sym] = result

                print(f"  [{sym}] ${result['price']:,.2f} -> {action} ({result['confidence']:.0%}) Oy:{result.get('consensus', 0)}")

                if action in ["BUY", "SELL"] and result["confidence"] >= settings.min_confidence:
                    consensus = result.get("consensus", 0)
                    existing_pos = trader.get_position(sym)

                    if action == "SELL" and not existing_pos:
                        action = "HOLD"

                    if action == "BUY" and consensus >= 2:
                        self.last_signals[sym] = {
                            "action": action, "confidence": result["confidence"],
                            "price": result["price"], "reason": "; ".join(result["reasons"][:3]),
                            "rsi": result["rsi"], "time": self.last_scan,
                            "consensus": consensus
                        }
                        self._send_signal(sym, action, result["confidence"], result["price"],
                                          "; ".join(result["reasons"][:3]), result)

                    elif action == "SELL" and consensus >= 2:
                        self.last_signals[sym] = {
                            "action": action, "confidence": result["confidence"],
                            "price": result["price"], "reason": "; ".join(result["reasons"][:3]),
                            "rsi": result["rsi"], "time": self.last_scan,
                            "consensus": consensus
                        }
                        self._send_signal(sym, action, result["confidence"], result["price"],
                                          "; ".join(result["reasons"][:3]), result)

            except Exception as e:
                print(f"  [{sym}] HATA: {e}")
                new_results.append({
                    "symbol": sym, "action": "HOLD", "confidence": 0,
                    "price": 0, "rsi": 0, "volume_ratio": 0, "reason": str(e)[:50]
                })

        self.scan_results = new_results

        if self.total_scans == 1 or self.total_scans % 3 == 0:
            self._send_agent_report()

        self._check_ai_alerts()

    def _send_agent_report(self):
        for sym, result in self.agent_results.items():
            summary = result.get("summary", {})
            agent_statuses = summary.get("agent_statuses", [])
            direction = summary.get("direction", "BEKLE")
            confidence = summary.get("confidence", 0)
            consensus = summary.get("consensus", 0)

            action = "BUY" if direction == "ALIS" else "SELL" if direction == "SATIS" else "NEUTRAL"
            price = result.get("price", 0)
            reason = "; ".join(result.get("reasons", [])[:3])

            if action in ["BUY", "SELL"] and consensus >= 3:
                self.memory.record_prediction(sym, action, confidence, price, result, reason, consensus)

            msg = (
                f"<b>AI RAPOR - {sym}</b>  {self.last_scan}\n\n"
                f"Karar: <b>{direction}</b>  Guven: <b>{confidence:.0%}</b>\n"
                f"Oy Birligi: {consensus}/6 agent\n\n"
            )
            for status in agent_statuses:
                if "ALIS" in status:
                    msg += f"  {status}\n"
                elif "SATIS" in status:
                    msg += f"  {status}\n"
                else:
                    msg += f"  {status}\n"

            if result.get("reasons"):
                msg += f"\n<b>Nedenler:</b>\n"
                for r in result["reasons"][:5]:
                    msg += f"  {r}\n"

            tg.send(msg, silent=True)

    def _send_signal(self, symbol, action, confidence, price, reason, indicators):
        self.signals_sent += 1
        consensus = indicators.get("consensus", 0) if indicators else 0

        if action == "BUY":
            self.memory.record_signal(symbol, action, confidence, price, indicators, reason)
            self._buy_counter += 1
            self._pending_buys[self._buy_counter] = {
                "symbol": symbol, "action": action,
                "confidence": confidence, "price": price,
                "reason": reason, "indicators": indicators,
                "time": datetime.now().isoformat(), "recorded": False
            }
            trade_id = self._buy_counter
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

        ai_engine.record_outcome(symbol, "BUY", 0, entry_price, indicators, outcome, pnl_usd)

        if isinstance(indicators, dict) and "agents" in indicators:
            for agent_key, agent_result in indicators["agents"].items():
                if agent_result.get("direction") == "BUY" and agent_result.get("confidence", 0) > 0.5:
                    ml_agent.record_outcome(
                        symbol, "BUY", agent_result["confidence"],
                        entry_price, indicators, outcome, pnl_usd
                    )

        self.memory.record_signal(symbol, "BUY", 0, entry_price, indicators, f"Sonuc: {outcome}")
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
                "agent_results": {k: {
                    "direction": v.get("direction"),
                    "confidence": v.get("confidence"),
                    "buy_score": v.get("buy_score", 0),
                    "sell_score": v.get("sell_score", 0),
                    "consensus": v.get("consensus", 0),
                    "agents": {ak: {
                        "direction": av.get("direction"),
                        "confidence": av.get("confidence"),
                        "reason": av.get("reason", "")[:60]
                    } for ak, av in v.get("agents", {}).items()},
                    "reasons": v.get("reasons", [])[:5]
                } for k, v in self.agent_results.items()},
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
        predictions = self.memory.get_predictions(20)
        return {
            "stats": memory_stats,
            "recent": self.memory.get_recent(10),
            "ai": ai_stats,
            "predictions": predictions
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
