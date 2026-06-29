import time
import threading
from datetime import datetime, date
from src.config import settings
from src.trader import trader
from src.executor import executor
from src.analyzer import analyzer
from src.news import news_fetcher
from src.quant_agent import quant_agent
from src.telegram import tg


class Bot:
    def __init__(self):
        self.running = False
        self.paused = False
        self.auto_trade = False
        self.total_scans = 0
        self.last_scan = None
        self.last_action = None
        self.last_notified_action = None
        self.bekleyen_alis = None
        self.bekleyen_satis = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.paused = False
        tg.send(
            f"<b>BTC BOT BASLATILDI</b>\n\n"
            f"Her {settings.check_interval}s'de bir analiz\n"
            f"Mod: ONAYLI\n"
            f"Islem: {settings.executor_mode.upper()}"
        )
        threading.Thread(target=self._main_loop, daemon=True).start()

    def stop(self):
        self.running = False
        tg.send("<b>BOT DURDURULDU</b>")

    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def _main_loop(self):
        while self.running:
            if not self.paused:
                self._check_sl_tp()
                try:
                    self.scan()
                except Exception as e:
                    print(f"[BOT] Hata: {e}")
            time.sleep(settings.check_interval)

    def _check_sl_tp(self):
        pos = executor.get_position()
        if not pos:
            return
        price = trader.get_price()
        entry = pos["avg_entry_price"]
        pl_pct = (price - entry) / entry * 100

        state = quant_agent.state
        sl = state.get("son_sl", 0)
        tp = state.get("son_tp", 0)

        if sl > 0 and price <= sl:
            print(f"[SL] Tetiklendi: ${price:,.2f} <= ${sl:,.2f}")
            tg.send(f"\u26a0\ufe0f <b>STOP-LOSS TETIKLENDI</b>\n\nFiyat: ${price:,.2f}\nKayip: %{pl_pct:.2f}")
            self._satisi_gerceklestir("Stop-loss")
            return

        if tp > 0 and price >= tp:
            print(f"[TP] Tetiklendi: ${price:,.2f} >= ${tp:,.2f}")
            tg.send(f"\u2705 <b>TAKE-PROFIT TETIKLENDI</b>\n\nFiyat: ${price:,.2f}\nKar: %{pl_pct:.2f}")
            self._satisi_gerceklestir("Take-profit")
            return

        sl_tp_str = f"SL:${sl:,.0f} TP:${tp:,.0f}" if sl > 0 else ""
        print(f"[MONITOR] ${price:,.2f} | %{pl_pct:+.2f} {sl_tp_str}")

    def scan(self):
        self.total_scans += 1
        self.last_scan = datetime.now().strftime('%H:%M:%S')
        print(f"\n[SCAN #{self.total_scans}] {self.last_scan}")

        df = trader.get_bars(100)
        if df.empty:
            print("  Veri yok")
            return

        teknik = analyzer.analyze(df)
        if not teknik:
            print("  Analiz basarisiz")
            return

        price = teknik["price"]
        haberler = news_fetcher.fetch_bitcoin_news(3)

        account = executor.get_account()
        pos = executor.get_position()

        if pos:
            usdt_bakiye = account.get("cash", 0)
            btc_bakiye = pos["qty"]
            acik_pozisyon = True
            giris_fiyati = pos["avg_entry_price"]
        else:
            usdt_bakiye = account.get("portfolio_value", 0)
            btc_bakiye = 0
            acik_pozisyon = False
            giris_fiyati = 0

        portfoy = {
            "usdt_bakiye": usdt_bakiye,
            "btc_bakiye": btc_bakiye,
            "acik_pozisyon": acik_pozisyon,
            "giris_fiyati": giris_fiyati,
        }

        state = quant_agent.get_state()
        hafiza = {
            "son_islem_kar_zarar": state.get("son_islem_kar_zarar", 0),
            "son_hatalar": [],
            "aktif_strateji_notu": state.get("aktif_strateji_notu", ""),
        }

        karar = quant_agent.analyze(teknik, haberler, portfoy, hafiza)
        action = karar["action"]
        confidence = karar["confidence_score"]

        self.last_action = action

        if action == "BUY" and not acik_pozisyon:
            if self.last_notified_action != "BUY" and self.bekleyen_alis is None:
                sl = karar["execution"]["stop_loss"]
                tp = karar["execution"]["take_profit"]
                quant_agent.state["son_sl"] = sl
                quant_agent.state["son_tp"] = tp
                quant_agent._save_state()
                reason = karar["memory_update"]["aktif_strateji_notu"]
                tg.send_buy_signal(price, confidence * 100, sl, tp, reason)
                self.bekleyen_alis = karar
                self.last_notified_action = "BUY"
                print(f"  -> ALIS bildirimi gonderildi (guven: %{confidence:.0%})")
            else:
                print(f"  -> ALIS sinyali (bekliyor, guven: %{confidence:.0%})")

        elif action == "SELL" and acik_pozisyon:
            if self.last_notified_action != "SELL" and self.bekleyen_satis is None:
                entry = giris_fiyati
                kar_zarar = pos["unrealized_pl"]
                yuzde = (price - entry) / entry * 100
                reason = karar["memory_update"]["aktif_strateji_notu"]
                tg.send_sell_signal(price, entry, kar_zarar, yuzde, reason)
                self.bekleyen_satis = karar
                self.last_notified_action = "SELL"
                print(f"  -> SATIS bildirimi gonderildi (guven: %{confidence:.0%})")
            else:
                print(f"  -> SATIS sinyali (bekliyor, guven: %{confidence:.0%})")
        else:
            print(f"  -> {action} (%{confidence:.0%})")

    def alisi_onayla(self):
        if self.bekleyen_alis is None:
            tg.send("Bekleyen alis yok.")
            return
        karar = self.bekleyen_alis
        size_pct = karar["execution"]["size_percentage"]
        try:
            result = executor.buy(size_pct)
            if result:
                tg.send_islem_sonucu("BUY", result["price"], result["qty"])
                self.bekleyen_alis = None
                self.bekleyen_satis = None
                self.last_notified_action = None
                print(f"[BOT] ALIS gerceklesti: {result['qty']:.6f} BTC @ ${result['price']:,.2f}")
        except Exception as e:
            tg.send(f"<b>ALIS HATASI</b>\n<code>{str(e)[:200]}</code>")

    def satisi_onayla(self):
        if self.bekleyen_satis is None:
            tg.send("Bekleyen satis yok.")
            return
        self._satisi_gerceklestir("Kullanici onayi")

    def _satisi_gerceklestir(self, sebep):
        try:
            result = executor.sell()
            if result:
                pl = result.get("pl", 0)
                quant_agent.islem_sonucu_kaydet(pl)
                tg.send_islem_sonucu("SELL", result["price"], result["qty"], pl)
                self.bekleyen_alis = None
                self.bekleyen_satis = None
                self.last_notified_action = None
                quant_agent.state["son_sl"] = 0
                quant_agent.state["son_tp"] = 0
                quant_agent._save_state()
                print(f"[BOT] SATIS gerceklesti: K/Z ${pl:+,.2f} ({sebep})")
        except Exception as e:
            tg.send(f"<b>SATIS HATASI</b>\n<code>{str(e)[:200]}</code>")

    def get_status(self):
        try:
            acc = executor.get_account()
            pos = executor.get_position()
            state = quant_agent.get_state()
            return {
                "running": self.running,
                "paused": self.paused,
                "auto_trade": self.auto_trade,
                "total_scans": self.total_scans,
                "last_scan": self.last_scan,
                "portfolio_value": acc.get("portfolio_value", 0),
                "cash": acc.get("cash", 0),
                "pozisyon_durumu": "Aktif" if pos else "Yok",
                "kar_zarar": pos["unrealized_pl"] if pos else 0,
                "son_karar": self.last_action,
                "toplam_islem": state.get("toplam_islem", 0),
                "kazanma": state.get("kazanma", 0),
                "kaybetme": state.get("kaybetme", 0),
            }
        except Exception as e:
            return {"running": self.running, "error": str(e)}


bot = Bot()


def setup_telegram():
    tg.on_start(lambda: bot.start())
    tg.on_stop(lambda: bot.stop())
    tg.on_scan(lambda: bot.scan())
    tg.on_buy_onay(lambda: bot.alisi_onayla())
    tg.on_sell_onay(lambda: bot.satisi_onayla())
    tg.on_status(lambda: tg.send_durum(bot.get_status()))
    tg.on_oto(lambda: setattr(bot, 'auto_trade', True) or tg.send("Mod: OTO"))
    tg.on_manuel(lambda: setattr(bot, 'auto_trade', False) or tg.send("Mod: ONAYLI"))
    tg.start_polling()


def toggle_auto(enabled):
    bot.auto_trade = enabled
