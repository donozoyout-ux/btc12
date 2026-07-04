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
        self._last_error_sent = None
        self._error_cooldown = 0
        self._alis_hata_saati = 0
        self._satis_hata_saati = 0
        self._alpaca_uyari_gonderildi = False
        self._son_alis_saati = 0
        self._min_hold_sure = 1800
        self._alis_onay_sayisi = 0
        self._alis_onay_gerekli = 3
        self._son_buy_sinyal_fiyati = 0

    def start(self, mesaj_gonder=True):
        if self.running:
            if mesaj_gonder:
                tg.send("Bot zaten calisiyor. <code>/stop</code> ile durdurabilirsin.")
            return
        self.running = True
        self.paused = False
        self.auto_trade = True
        if mesaj_gonder:
            try:
                tg.send(
                    f"<b>BTC BOT BASLATILDI</b>\n\n"
                    f"Her {settings.check_interval}s'de bir analiz\n"
                    f"Mod: <b>OTO</b>\n"
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

        if sl > 0 and pl_pct > 1.0:
            new_sl = round(entry + (price - entry) * 0.4, 2)
            if new_sl > sl:
                quant_agent.state["son_sl"] = new_sl
                quant_agent._save_state()
                print(f"[TRAILING] SL guncellendi: ${new_sl:,.2f} (kar: %{pl_pct:.2f})")

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
            err_key = str(e)[:50]
            now = time.time()
            if err_key != self._last_error_sent and now - self._error_cooldown > 300:
                tg.send(f"Veri hatasi: {str(e)[:100]}")
                self._last_error_sent = err_key
                self._error_cooldown = now
            return

        if df.empty:
            print("  Veri yok")
            self.son_hata = "Veri yok"
            return

        teknik = analyzer.analyze(df)
        if not teknik:
            print("  Analiz basarisiz")
            self.son_hata = "Analiz basarisiz"
            if now - self._error_cooldown > 300:
                tg.send("Analiz basarisiz - veri kalitesi dusuk")
                self._error_cooldown = now
            return

        teknik["orderbook"] = trader.get_orderbook()

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
            if self._son_buy_sinyal_fiyati > 0:
                fiyat_fark = abs(price - self._son_buy_sinyal_fiyati) / self._son_buy_sinyal_fiyati * 100
                if fiyat_fark < 2.0:
                    self._alis_onay_sayisi += 1
                else:
                    self._alis_onay_sayisi = 1
                    self._son_buy_sinyal_fiyati = price
            else:
                self._alis_onay_sayisi = 1
                self._son_buy_sinyal_fiyati = price

            print(f"  -> ALIS sinyali #{self._alis_onay_sayisi}/{self._alis_onay_gerekli} (guven: %{confidence:.0%})")

            if self._alis_onay_sayisi < self._alis_onay_gerekli:
                return

            self._alis_onay_sayisi = 0
            self._son_buy_sinyal_fiyati = 0

            if self.auto_trade:
                self.bekleyen_alis = karar
                quant_agent.state["son_sl"] = karar["execution"]["stop_loss"]
                quant_agent.state["son_tp"] = karar["execution"]["take_profit"]
                quant_agent._save_state()
                self.alisi_onayla()
            elif self.last_notified_action != "BUY" and self.bekleyen_alis is None:
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
            pos_suresi = time.time() - self._son_alis_saati if self._son_alis_saati > 0 else 9999
            if pos_suresi < self._min_hold_sure:
                print(f"  -> SATIS ENGELLENDI (bekleme: {pos_suresi:.0f}s / {self._min_hold_sure}s)")
                return
            if self.auto_trade:
                self.bekleyen_satis = karar
                self._satisi_gerceklestir("Oto satis")
            elif self.last_notified_action != "SELL" and self.bekleyen_satis is None:
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

        if self.total_scans == 1:
            rsi_de = teknik.get("rsi", "?")
            ema_de = teknik.get("ema_cross", "?")
            tg.send(
                f"<b>Bot aktif</b> | 15s tarama\n\n"
                f"Fiyat: <code>${price:,.0f}</code>\n"
                f"RSI: <code>{rsi_de}</code> | EMA: <code>{ema_de}</code>",
                silent=True
            )

    def alisi_onayla(self):
        if self.bekleyen_alis is None:
            tg.send("Bekleyen alis yok.")
            return
        karar = self.bekleyen_alis
        size_pct = karar["execution"]["size_percentage"]
        try:
            result = executor.buy(size_pct)
            if result:
                is_sim = result.get("order_id", "") == "dry_buy"
                if is_sim:
                    if not self._alpaca_uyari_gonderildi:
                        self._alpaca_uyari_gonderildi = True
                        self.auto_trade = False
                        tg.send(
                            f"\u26a0\ufe0f <b>Alpaca baglanti hatasi</b>\n\n"
                            f"API anahtarlari gecersiz. Bot <b>manuel moda</b> gecirildi.\n"
                            f"Simulasyon modunda calisiyor.\n\n"
                            f"Dueltmek icin:\n"
                            f"1. Guncel API key gir\n"
                            f"2. <code>/oto</code> ile tekrar aktif et"
                        )
                        print("[BOT] Alpaca unauthorized, auto_trade kapatildi, simulasyon modu")
                        return
                    tg.send(f"\U0001f7e2 <b>SIMULASYON ALIS</b>\n\n"
                            f"Miktar: <code>{result['qty']:.6f} BTC</code>\n"
                            f"Fiyat: <code>${result['price']:,.2f}</code>\n\n"
                            f"\u26a0\ufe0f Gercek Alpaca emri gonderilemedi, simulasyon")
                else:
                    tg.send_islem_sonucu("BUY", result["price"], result["qty"])
                    quant_agent.state["son_giris_fiyati"] = result["price"]
                    quant_agent._save_state()
                    db.save_trade("BUY", result["price"], result["qty"], 0, "Kullanici onayi", result["price"])
                self.bekleyen_alis = None
                self.bekleyen_satis = None
                self.last_notified_action = None
                self._alis_hata_saati = 0
                self._son_alis_saati = time.time()
                print(f"[BOT] {'SIMULASYON ' if is_sim else ''}ALIS gerceklesti: {result['qty']:.6f} BTC @ ${result['price']:,.2f}")
        except Exception as e:
            err_same = str(e)[:80] == self._last_error_sent
            cooldown_active = (time.time() - self._alis_hata_saati) < 300
            if err_same and cooldown_active:
                print(f"[BOT] ALIS HATASI tekrari engellendi (cooldown): {str(e)[:100]}")
                return
            self._alis_hata_saati = time.time()
            self._last_error_sent = str(e)[:80]
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
                is_sim = result.get("order_id", "") == "dry_sell"
                if is_sim:
                    tg.send(f"\U0001f534 <b>SIMULASYON SATIS</b>\n\n"
                            f"Miktar: <code>{result['qty']:.6f} BTC</code>\n"
                            f"Fiyat: <code>${result['price']:,.2f}</code>\n"
                            f"K/Z: <code>${pl:+,.2f}</code>\n"
                            f"Sebep: {sebep}\n\n"
                            f"\u26a0\ufe0f Simulasyon modu")
                else:
                    quant_agent.islem_sonucu_kaydet(pl)
                    tg.send_islem_sonucu("SELL", result["price"], result["qty"], pl)
                    db.save_trade("SELL", result["price"], result["qty"], pl, sebep, quant_agent.state.get("son_giris_fiyati", 0))
                self.bekleyen_alis = None
                self.bekleyen_satis = None
                self.last_notified_action = None
                quant_agent.state["son_sl"] = 0
                quant_agent.state["son_tp"] = 0
                quant_agent._save_state()
                self._satis_hata_saati = 0
                print(f"[BOT] SATIS gerceklesti: K/Z ${pl:+,.2f} ({sebep})")
        except Exception as e:
            now = time.time()
            err_key = str(e)[:80]
            is_unauth = "unauthorized" in str(e).lower() or "auth" in str(e).lower() or "401" in str(e)
            if is_unauth and not self._alpaca_uyari_gonderildi:
                self._alpaca_uyari_gonderildi = True
                self.auto_trade = False
                tg.send(f"\u26a0\ufe0f <b>Alpaca baglanti hatasi</b> - Manuel moda gecildi")
                print("[BOT] Alpaca unauthorized (sell), simulasyon modu")
                return
            err_same = err_key == self._last_error_sent
            cooldown_active = (now - self._satis_hata_saati) < 300
            if err_same and cooldown_active:
                print(f"[BOT] SATIS HATASI tekrari engellendi (cooldown): {str(e)[:100]}")
                return
            self._satis_hata_saati = now
            self._last_error_sent = err_key
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

    def cmd_fiyat(self):
        try:
            price = trader.get_price()
            df = trader.get_bars(50)
            teknik = analyzer.analyze(df) if not df.empty else None
            if teknik:
                msg = (
                    f"<b>BTC FIYAT</b>\n\n"
                    f"Fiyat: <code>${price:,.2f}</code>\n"
                    f"RSI: <code>{teknik['rsi']}</code>\n"
                    f"EMA: <code>{teknik['ema_cross'].upper()}</code>\n"
                    f"MACD: <code>{teknik['macd_hist']:+.2f}</code>\n"
                    f"BB: <code>%{teknik['bb_pct']*100:.1f}</code>\n"
                    f"Hacim: <code>{teknik['vol_ratio']}x</code>\n"
                    f"Destek: <code>${teknik['support']:,.0f}</code>\n"
                    f"Direnc: <code>${teknik['resistance']:,.0f}</code>"
                )
            else:
                msg = f"<b>BTC FIYAT</b>\n\nFiyat: <code>${price:,.2f}</code>"
            tg.send(msg)
        except Exception as e:
            tg.send(f"Fiyat alinamadi: {e}")

    def cmd_portfoy(self):
        try:
            acc = executor.get_account()
            pos = executor.get_position()
            price = trader.get_price()
            msg = f"<b>PORTFOY</b>\n\nNakit: <code>${acc.get('cash', 0):,.2f}</code>\nToplam: <code>${acc.get('portfolio_value', 0):,.2f}</code>"
            if pos:
                pl = pos.get("unrealized_pl", 0)
                pl_pct = (price - pos["avg_entry_price"]) / pos["avg_entry_price"] * 100
                msg += (
                    f"\n\nPozisyon: <code>{pos['qty']:.6f} BTC</code>\n"
                    f"Giris: <code>${pos['avg_entry_price']:,.2f}</code>\n"
                    f"K/Z: <b>{'🟢' if pl >= 0 else '🔴'} ${pl:+,.2f}</b> (%{pl_pct:+.2f})"
                )
            tg.send(msg)
        except Exception as e:
            tg.send(f"Portfoy alinamadi: {e}")

    def cmd_kar(self):
        try:
            state = quant_agent.get_state()
            stats = db.get_stats()
            msg = (
                f"<b>KAR/ZARAR</b>\n\n"
                f"Toplam Islem: <code>{stats.get('toplam_islem', 0)}</code>\n"
                f"Kazanc: <code>{stats.get('kazanma', 0)}</code>\n"
                f"Kayip: <code>{stats.get('kaybetme', 0)}</code>\n"
                f"Basarim: <code>%{stats.get('kazanma_orani', 0)}</code>\n"
                f"Net K/Z: <b>${stats.get('toplam_kar_zarar', 0):+,.2f}</b>\n"
                f"Ardisik Kayip: <code>{state.get('ardisik_kayip', 0)}</code>"
            )
            tg.send(msg)
        except Exception as e:
            tg.send(f"Kar durumu alinamadi: {e}")

    def cmd_son(self):
        try:
            trades = db.get_trade_history(5)
            if not trades:
                tg.send("Henuz islem yok.")
                return
            lines = ["<b>SON 5 ISLEM</b>\n"]
            for t in trades:
                emoji = "🟢" if t["pnl"] >= 0 else "🔴"
                lines.append(
                    f"{emoji} {t['action']} ${t['price']:,.2f} | "
                    f"{'K/Z: $' + t['pnl']:+,.2f' if t['pnl'] else ''}"
                )
            tg.send("\n".join(lines))
        except Exception as e:
            tg.send(f"Gecmis alinamadi: {e}")

    def cmd_yardim(self):
        msg = (
            "<b>KOMUTLAR</b>\n\n"
            "<code>/start</code> - Botu baslat\n"
            "<code>/stop</code> - Botu durdur\n"
            "<code>/scan</code> - El ile tarama\n"
            "<code>/status</code> - Durum raporu\n"
            "<code>/fiyat</code> - BTC fiyat + indikatorler\n"
            "<code>/portfoy</code> - Portfoy detayi\n"
            "<code>/kar</code> - Kar/zarar ozeti\n"
            "<code>/son</code> - Son 5 islem\n"
            "<code>/oto</code> - Oto-alim modu\n"
            "<code>/manuel</code> - Onayli mod\n"
            "<code>/onay</code> - Alisi onayla\n"
            "<code>/sat</code> - Satisi onayla\n"
            "<code>/iptal</code> - Islemi iptal\n"
            "<code>/miktar 100</code> - Miktar ayarla\n"
            "<code>/artir 50</code> - Miktar artir\n"
            "<code>/azalt 25</code> - Miktar azalt\n"
            "<code>/durdur</code> - Taramayi duraklat\n"
            "<code>/devam</code> - Taramaya devam\n"
            "<code>/sifirla</code> - Bekleyen sinyalleri temizle"
        )
        tg.send(msg)

    def cmd_durdur(self):
        self.paused = True
        tg.send("⏸ Tarama duraklatildi. <code>/devam</code> ile devam et.")

    def cmd_devam(self):
        self.paused = False
        tg.send("▶ Tarama devam ediyor.")

    def cmd_sifirla(self):
        self.bekleyen_alis = None
        self.bekleyen_satis = None
        self.last_notified_action = None
        tg.send("Bekleyen sinyaller temizlendi.")

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
    tg.on_oto(lambda: toggle_auto(True))
    tg.on_manuel(lambda: toggle_auto(False))
    tg.on_miktar(lambda val: bot.miktar_goster(val))
    tg.on_artir(lambda val: bot.miktar_artir(val))
    tg.on_azalt(lambda val: bot.miktar_azalt(val))
    tg.on_fiyat(lambda: bot.cmd_fiyat())
    tg.on_portfoy(lambda: bot.cmd_portfoy())
    tg.on_kar(lambda: bot.cmd_kar())
    tg.on_son(lambda: bot.cmd_son())
    tg.on_yardim(lambda: bot.cmd_yardim())
    tg.on_durdur(lambda: bot.cmd_durdur())
    tg.on_devam(lambda: bot.cmd_devam())
    tg.on_sifirla(lambda: bot.cmd_sifirla())
    tg.start_polling()


def toggle_auto(enabled):
    bot.auto_trade = enabled
    if enabled:
        bot._alpaca_uyari_gonderildi = False
        if executor._client is None and settings.alpaca_api_key and settings.alpaca_secret_key:
            try:
                executor._init_alpaca()
                print("[BOT] Alpaca yeniden baglaniyor...")
            except:
                pass
        tg.send("Mod: <b>OTO</b>")
    else:
        tg.send("Mod: <b>ONAYLI</b>")
