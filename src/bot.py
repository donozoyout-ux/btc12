import time
import threading
from datetime import datetime, date
from src.config import settings
from src.trader import trader
from src.executor import executor
from src.analyzer import analyzer
from src.news import news_fetcher
from src.quant_agent import quant_agent
from src.database import db
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
        self.son_hata = None

    def start(self, mesaj_gonder=True):
        if self.running:
            return
        self.running = True
        self.paused = False
        if mesaj_gonder:
            try:
                tg.send(
                    f"<b>BTC BOT BASLATILDI</b>\n\n"
                    f"Her {settings.check_interval}s'de bir analiz\n"
                    f"Mod: ONAYLI\n"
                    f"Islem: {settings.executor_mode.upper()}"
                )
            except:
                pass
        print("[BOT] Baslatildi, ilk tarama yapiliyor...")
        try:
            self.scan()
        except Exception as e:
            print(f"[BOT] Ilk tarama hatasi: {e}")
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

        try:
            df = trader.get_bars(100)
        except Exception as e:
            print(f"  Veri hatasi: {e}")
            self.son_hata = f"Veri: {e}"
            return

        if df.empty:
            print("  Veri yok")
            self.son_hata = "Veri yok"
            return

        teknik = analyzer.analyze(df)
        if not teknik:
            print("  Analiz basarisiz")
            self.son_hata = "Analiz basarisiz"
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

        haber_sentiment = sum(1 for h in haberler if h.get("sentiment") == "pozitif") - sum(1 for h in haberler if h.get("sentiment") == "negatif")
        db.save_scan(
            price=price, rsi=teknik.get("rsi"), ema_cross=teknik.get("ema_cross"),
            macd_hist=teknik.get("macd_hist"), vol_ratio=teknik.get("vol_ratio"),
            haber_sentiment=haber_sentiment, action=action, confidence=confidence,
            stop_loss=karar.get("execution", {}).get("stop_loss", 0),
            take_profit=karar.get("execution", {}).get("take_profit", 0),
            system_log=karar.get("system_log", "")
        )

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
                db.save_signal("BUY", price, confidence)
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
                db.save_signal("SELL", price, confidence)
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
                quant_agent.state["son_giris_fiyati"] = result["price"]
                quant_agent._save_state()
                db.save_trade("BUY", result["price"], result["qty"], 0, "Kullanici onayi", result["price"])
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
                db.save_trade("SELL", result["price"], result["qty"], pl, sebep, quant_agent.state.get("son_giris_fiyati", 0))
                self.bekleyen_alis = None
                self.bekleyen_satis = None
                self.last_notified_action = None
                quant_agent.state["son_sl"] = 0
                quant_agent.state["son_tp"] = 0
                quant_agent._save_state()
                print(f"[BOT] SATIS gerceklesti: K/Z ${pl:+,.2f} ({sebep})")
        except Exception as e:
            tg.send(f"<b>SATIS HATASI</b>\n<code>{str(e)[:200]}</code>")

    def miktar_goster(self, deger=None):
        if deger is None:
            tg.send(f"<b>ISLEM MIKTARI</b>\n\nGuncel: <code>${settings.position_size_usd:.0f}</code>\n\nDegistirmek icin: <code>/miktar 100</code>\nArtirmak icin: <code>/artir 50</code>\nAzaltmak icin: <code>/azalt 25</code>")
        else:
            if deger < 10:
                tg.send("Minimum miktar: $10")
                return
            settings.position_size_usd = float(deger)
            tg.send(f"<b>MIKTAR GUNCELLENDI</b>\n\nYeni islem miktari: <code>${settings.position_size_usd:.0f}</code>")

    def miktar_artir(self, miktar):
        yeni = settings.position_size_usd + miktar
        if yeni > 10000:
            tg.send("Maksimum miktar: $10,000")
            return
        settings.position_size_usd = yeni
        tg.send(f"<b>MIKTAR ARTIRILDI</b>\n\nYeni: <code>${settings.position_size_usd:.0f}</code>")

    def miktar_azalt(self, miktar):
        yeni = settings.position_size_usd - miktar
        if yeni < 10:
            tg.send("Minimum miktar: $10")
            return
        settings.position_size_usd = yeni
        tg.send(f"<b>MIKTAR AZALTILDI</b>\n\nYeni: <code>${settings.position_size_usd:.0f}</code>")

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
                "son_hata": self.son_hata,
                "son_fiyat": trader.get_price() if self.running else 0,
            }
        except Exception as e:
            return {"running": self.running, "error": str(e), "son_hata": self.son_hata}


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
    tg.on_miktar(lambda val: bot.miktar_goster(val))
    tg.on_artir(lambda val: bot.miktar_artir(val))
    tg.on_azalt(lambda val: bot.miktar_azalt(val))
    tg.start_polling()


def toggle_auto(enabled):
    bot.auto_trade = enabled
