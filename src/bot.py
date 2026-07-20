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
from src.ai_model import ai_model
from src.agents import consensus
from src import llm_agent
from src import self_improve


class Bot:
    def __init__(self):
        self.running = False
        self.paused = False
        self.total_scans = 0
        self.last_scan = None
        self.last_action = None
        self.bekleyen_alis = None
        self.bekleyen_satis = None
        self.son_hata = None
        self._son_alis_saati = 0
        self.last_scan_data = {}
        self.last_news = []
        self.last_gemini_debate = None
        self._error_cooldown = 0
        self._last_signal_notify = 0
        self._last_signal_action = None

    def start(self, mesaj_gonder=True):
        if self.running:
            # Zaten çalışıyorsa sadece duraklatılmışsa devam ettir
            if self.paused:
                self.paused = False
                if mesaj_gonder:
                    tg.send("▶ Bot duraklatma kaldırıldı, taramaya devam ediliyor.")
                return
            if mesaj_gonder:
                tg.send("Bot zaten calisiyor. <code>/stop</code> ile durdurabilirsin.")
            return
        self.running = True
        self.paused = False
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
        print("[BOT] Baslatildi, tarama dongusu baslatiliyor...")
        threading.Thread(target=self._main_loop, daemon=True).start()
        # İlk taramayı ayrı çağır (hata olsa bile döngü çalışmaya devam eder)
        try:
            self.scan()
        except Exception as e:
            print(f"[BOT] Ilk tarama hatasi: {e}")

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
        # NOT: Otomatik SL/TP SATISI KALDIRILDI. Pozisyonlar yalnizca scan()
        # icindeki SELL sinyaliyle kapanir. Bu fonksiyon SADECE pasif
        # izleyicidir; fiyat/kar-zarar/maliyet bazini raporlar, satis yapmaz.
        pos = executor.get_position()
        if not pos:
            return
        price = trader.get_price()
        entry = pos["avg_entry_price"]
        pl_pct = (price - entry) / entry * 100
        cost_basis = pos["qty"] * entry
        print(f"[MONITOR] ${price:,.2f} | %{pl_pct:+.2f} | Maliyet bazı: ${cost_basis:,.2f}")

    def _ai_skor(self, teknik, teknik_5m=None):
        prob, conf = ai_model.predict(teknik, teknik_5m)
        return prob

    def scan(self):
        self.total_scans += 1
        self.last_scan = datetime.now().strftime('%H:%M:%S')
        print(f"\n[SCAN #{self.total_scans}] {self.last_scan}")

        try:
            df = trader.get_bars(500)
            df_5m = None
            try:
                df_5m = trader.get_bars(100, '5m')
            except:
                pass
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
            now = time.time()
            if now - self._error_cooldown > 300:
                tg.send("Analiz basarisiz - veri kalitesi dusuk")
                self._error_cooldown = now
            return

        try:
            teknik["orderbook"] = trader.get_orderbook()
        except Exception as e:
            print(f"[SCAN] Orderbook alinamadi: {e}")
            teknik["orderbook"] = {}

        teknik_5m = analyzer.analyze(df_5m) if df_5m is not None and not df_5m.empty else None
        if teknik_5m:
            teknik_5m["orderbook"] = teknik.get("orderbook", {})

        # ─── Scalping (M10/M30) çoklu periyot beslemesi ───
        # RSI / MACD / EMA Cross gibi indikatörler 10m ve 30m mumlarından da
        # hesaplanıp ana 'teknik' sözlüğüne <periyot>_<gösterge> olarak eklenir.
        try:
            scalp = trader.get_scalp_indicators(limit=100)
            teknik = trader.merge_scalp_indicators(teknik, scalp)
            if scalp:
                tf_list = ", ".join(scalp.keys())
                print(f"[SCAN] Scalp periyotlari yüklendi: {tf_list}")
        except Exception as e:
            print(f"[SCAN] Scalp (M10/M30) veri hatasi: {e}")

        anomaly = ai_model.detect_anomaly(teknik["price"], teknik.get("vol_ratio", 1))
        if anomaly["is_anomaly"]:
            print(f"  [ANOMALI] Skor: {anomaly['anomaly_score']}")

        # Modeller egitilmemisse ilk taramada, sonrasinda her 50 taramada bir egit
        is_any_agent_untrained = not consensus.agents["trend"].is_trained
        if (self.total_scans % 50 == 0 or (self.total_scans == 1 and is_any_agent_untrained)) and not df.empty:
            self._train_models(df, teknik)

        # Periyodik otonom öz-değerlendirme (her 50 taramada)
        if self.total_scans % 50 == 0 and self.total_scans > 0:
            try:
                lesson = self_improve.review_and_adapt(db, consensus)
                if lesson:
                    print(f"[SELF-IMPROVE] periyodik: {lesson}")
            except Exception as e:
                print(f"[SELF-IMPROVE] periyodik hata: {e}")

        # ─── Beyinlerin otomatik yenilenmesi ───
        # Üst üste zarar serisi (MAX_CONSECUTIVE_LOSSES) tespit edilirse beyinler
        # kendini yeniler: stale dersler temizlenir, agresiflik/guven esigi sifirlanir,
        # modeller birikmis tarama gecmisiyle yeniden egitilir.
        if self.total_scans - getattr(self, "_last_refresh_scan", -9999) >= 10:
            ark = quant_agent.state.get("ardisik_kayip", 0)
            if ark >= settings.max_consecutive_losses:
                self.brain_refresh()
                self._last_refresh_scan = self.total_scans

        price = teknik["price"]
        try:
            haberler = news_fetcher.fetch_bitcoin_news(8)
        except Exception as e:
            print(f"[SCAN] Haber alinamadi: {e}")
            haberler = []

        account = executor.get_account()
        pos = executor.get_position()

        # Kendini geliştirme: konsensüs güven eşiğini öğrenilmiş değere çek
        try:
            _sp = self_improve.get_params()
            consensus.min_weighted_conf = _sp["min_confidence_threshold"]
        except Exception:
            pass

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

        # ─── Gemini 5-Brain AI Debate (konsensüse bağlanacak) ───
        # Konsensüs oylamasından ÖNCE çalıştırılır ki sonuç karara dahil olsun.
        try:
            ml_votes = consensus.last_votes if hasattr(consensus, 'last_votes') else {}
            from src import ai_brains
            brains_cfg = ai_brains.load_brains()
            lessons_cfg = self_improve.get_lessons(6)
            debate = llm_agent.run_debate(teknik, haberler, ml_votes, brains=brains_cfg, lessons=lessons_cfg)
            if debate:
                self.last_gemini_debate = debate
                # Güçlü 5-ajan sinyali için Telegram bildirimi (spam önlemek adına
                # yön değişince veya 10 dk geçince bir kez)
                try:
                    fd = debate.get("final_decision", "HOLD")
                    fc = float(debate.get("final_confidence", 0) or 0)
                    if fd in ("BUY", "SELL") and fc >= 0.50:
                        now = time.time()
                        if fd != self._last_signal_action or (now - self._last_signal_notify) > 600:
                            self._last_signal_notify = now
                            self._last_signal_action = fd
                            tg.send(f"📡 <b>5 AJAN SİNYALİ</b>\n\n"
                                    f"Yön: <b>{'AL' if fd == 'BUY' else 'SAT'}</b>\n"
                                    f"Güven: <b>%{fc*100:.0f}</b>\n"
                                    f"(Güçlü çoğunluk sağlandı, işlem değerlendirmesi yapılıyor)")
                except Exception:
                    pass
        except Exception as e:
            print(f"[LLM] Debate cagirma hatasi: {e}")

        try:
            karar = quant_agent.analyze(teknik, haberler, portfoy, hafiza, gemini_debate=self.last_gemini_debate)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[SCAN] Analiz hatasi (HOLD'a dusuldu): {e}")
            karar = {"action": "HOLD", "confidence_score": 0.0, "execution": {},
                     "system_log": f"ANALYZE_ERROR:{e}", "memory_update": {}}
        action = karar.get("action", "HOLD")
        confidence = karar.get("confidence_score", 0.0)
        self.last_scan_data = teknik
        self.last_news = haberler

        haber_sentiment = sum(1 for h in haberler if h.get("sentiment") == "pozitif") - sum(1 for h in haberler if h.get("sentiment") == "negatif")
        try:
            db.save_scan(
                price=price, rsi=teknik.get("rsi"), ema_cross=teknik.get("ema_cross"),
                macd_hist=teknik.get("macd_hist"), vol_ratio=teknik.get("vol_ratio"),
                haber_sentiment=haber_sentiment, action=action, confidence=confidence,
                stop_loss=karar.get("execution", {}).get("stop_loss", 0),
                take_profit=karar.get("execution", {}).get("take_profit", 0),
                system_log=karar.get("system_log", "")
            )
        except Exception as e:
            print(f"[SCAN] save_scan hatasi: {e}")

        self.last_action = action

        # --- Karar Kaydetme ---
        karar_sistemi = karar.get("system_log", "")
        strategy_action = karar.get("action", "HOLD")
        strategy_score = karar.get("confidence_score", 0.0)
        strategy_reason = karar.get("memory_update", {}).get("aktif_strateji_notu", "")
        if not strategy_reason:
            strategy_reason = "Konsensüs oylaması yapıldı"
        final_reason = karar_sistemi

        ai_prob = 0.5
        ai_veto = False
        executed = False

        if action == "BUY" and not acik_pozisyon:
            buy_cooldown = 60
            if time.time() - self._son_alis_saati < buy_cooldown:
                kalan = int(buy_cooldown - (time.time() - self._son_alis_saati))
                print(f"  -> ALIS COOLDOWN ({kalan}s kaldi)")
                return
            ai_prob, ai_conf = ai_model.predict(teknik, teknik_5m)
            print(f"  -> ALIS sinyali (guven: %{confidence:.0%} AI: {ai_prob:.0%})")

            is_strict = "STRICT" in karar_sistemi
            is_scalp = "SCALP" in karar_sistemi

            if not is_strict and not is_scalp and ai_prob < 0.4 and ai_conf > 0.2:
                print(f"  -> ALIS ENGELLENDI (AI dusus ongoruyor: %{ai_prob:.0%})")
                ai_veto = True
            else:
                self.bekleyen_alis = karar
                quant_agent.state["son_sl"] = karar.get("execution", {}).get("stop_loss", 0)
                quant_agent.state["son_tp"] = karar.get("execution", {}).get("take_profit", 0)
                quant_agent._save_state()
                # Sistem kendi işlem miktarına karar verir (dinamik boyut)
                try:
                    st = quant_agent.get_state()
                    tot = st.get("kazanma", 0) + st.get("kaybetme", 0)
                    wr = (st.get("kazanma", 0) / tot) if tot > 0 else 0.5
                    eq = account.get("portfolio_value", 0) or account.get("cash", 0)
                    try:
                        dailies = db.get_daily_pnl(1)
                        today_pnl = dailies[0]["pnl"] if dailies else 0
                    except Exception:
                        today_pnl = 0
                    target = eq * 0.01
                    dp = (today_pnl / target) if target > 0 else 0
                    if settings.executor_mode == "sim":
                        # Simülasyon: 500 TL (≈equity) sermayenin TAMAMI kullanılsın.
                        size = round(eq * 0.98, 2)
                    else:
                        size = self_improve.decide_position_size(eq, confidence, wr, 0.0, dp)
                    karar["execution"]["amount_usd"] = size
                    print(f"  -> DINAMIK ISLEM MIKTARI: ${size:.2f} (equity=${eq:.0f}, guven=%{confidence:.0%}, WR=%{wr:.0%})")
                except Exception as e:
                    print(f"[SELF] boyut hesaplama hatasi: {e}")
                # Girış anı gösterge snapshot'ı (geri besleme döngüsü için)
                try:
                    quant_agent.state["son_giris_teknik"] = {
                        "rsi": teknik.get("rsi"),
                        "macd_hist": teknik.get("macd_hist"),
                        "macd_hist_prev": teknik.get("macd_hist_prev"),
                        "bb_pct": teknik.get("bb_pct"),
                        "ema_cross": teknik.get("ema_cross"),
                        "vol_ratio": teknik.get("vol_ratio"),
                        "stoch_rsi": teknik.get("stoch_rsi"),
                    }
                    quant_agent._save_state()
                except Exception:
                    pass
                self._alisi_gerceklestir(karar)
                executed = True

        elif action == "SELL" and acik_pozisyon:
            ai_prob, ai_conf = ai_model.predict(teknik, teknik_5m)
            print(f"  -> SATIS sinyali (guven: %{confidence:.0%} AI: {ai_prob:.0%})")

            is_strict = "STRICT" in karar_sistemi
            is_scalp = "SCALP" in karar_sistemi

            if not is_strict and not is_scalp and ai_prob > 0.6 and ai_conf > 0.2:
                print(f"  -> SATIS ENGELLENDI (AI yukselis ongoruyor: %{ai_prob:.0%})")
                ai_veto = True
            else:
                self.bekleyen_satis = karar
                self._satisi_gerceklestir("AI sinyali")
                executed = True
        else:
            print(f"  -> {action} (%{confidence:.0%})")

        try:
            db.save_decision(
                strategy_action=strategy_action,
                strategy_score=round(strategy_score, 2),
                strategy_reason=strategy_reason,
                ai_prob=round(ai_prob, 3),
                ai_veto=ai_veto,
                final_action=action,
                final_reason=final_reason,
                price=price,
                executed=executed
            )
        except Exception as e:
            print(f"[SCAN] save_decision hatasi: {e}")

        if self.total_scans == 1:
            rsi_de = teknik.get("rsi", "?")
            ema_de = teknik.get("ema_cross", "?")
            tg.send(
                f"<b>Bot aktif</b> | 15s tarama\n\n"
                f"Fiyat: <code>${price:,.0f}</code>\n"
                f"RSI: <code>{rsi_de}</code> | EMA: <code>{ema_de}</code>",
                silent=True
            )

    def _train_models(self, df, teknik):
        """Mevcut df + teknik listesinden AI modeli ve 5 ajani yeniden egitir.
        Hem periyodik taramada hem brain_refresh()'te kullanilir."""
        try:
            teknik_listesi = []
            # Analiz motorunun en az 50 bar istemesi sebebiyle dilimleri 60 barlik yapiyoruz
            for i in range(len(df) - 60):
                temp_df = df.iloc[i : i + 60]
                if len(temp_df) >= 60:
                    t = analyzer.analyze(temp_df)
                    if t:
                        t["orderbook"] = (teknik or {}).get("orderbook", {})
                        teknik_listesi.append(t)
            if len(teknik_listesi) > 10:
                ok = ai_model.train(df, teknik_listesi, None)
                if ok:
                    ai_state = ai_model.get_state()
                    print(f"[AI] Egitildi: dogruluk=%{ai_state['accuracy']*100:.0f} tahmin={ai_state['prediction_count']}")
                # --- 5 Ajan Egitimi ---
                try:
                    closes = df["close"].values
                    N = len(closes)
                    LOOK_AHEAD = 5  # 5 bar ileriye bak

                    returns = []
                    for i in range(len(teknik_listesi)):
                        bar_idx = min(i + 59, N - 1)
                        future_idx = min(bar_idx + LOOK_AHEAD, N - 1)
                        cur_price = closes[bar_idx]
                        fut_price = closes[future_idx]
                        ret = (fut_price - cur_price) / cur_price * 100
                        returns.append(ret)

                    # Dinamik threshold: ust/alt %33 dilim BUY/SELL, orta %34 HOLD
                    import numpy as np
                    if len(returns) > 30:
                        sorted_ret = sorted(returns)
                        n = len(sorted_ret)
                        low_thresh = sorted_ret[int(n * 0.33)]
                        high_thresh = sorted_ret[int(n * 0.67)]

                        agent_training_data = []
                        for i, ret in enumerate(returns):
                            t = teknik_listesi[i]
                            if ret >= high_thresh:
                                label = 2  # BUY
                            elif ret <= low_thresh:
                                label = 0  # SELL
                            else:
                                label = 1  # HOLD
                            agent_training_data.append((t, label))

                        counts = {0: 0, 1: 0, 2: 0}
                        for _, lbl in agent_training_data:
                            counts[lbl] = counts.get(lbl, 0) + 1
                        print(f"[TRAINING] Egitim seti: BUY={counts[2]} HOLD={counts[1]} SELL={counts[0]} (Toplam:{len(agent_training_data)})")

                        if len(agent_training_data) > 15:
                            consensus.train_all(agent_training_data)
                except Exception as e:
                    print(f"[CONSENSUS] Ajan egitim hatasi: {e}")
                    import traceback
                    traceback.print_exc()
        except Exception as e:
            print(f"[TRAINING] Ana egitim adiminda hata: {e}")
            import traceback
            traceback.print_exc()

    def brain_refresh(self):
        """Zarar serisinde beyinleri otomatik yenile.
        - self_improve dersleri + agresiflik/guven esigi sifirlanir (stale ogrenme temizlenir)
        - AI model + 5 ajan, birikmis tarama gecmisiyle (ai_memory/scans) yeniden egitilir
        - Telegram bildirimi
        """
        print("[BRAIN_REFRESH] Beyinler otomatik yenileniyor...")
        try:
            from src import self_improve
            s = self_improve.load()
            # DERSLER KORUNUR (silinmez) - sadece agresiflik/guven sifirlanir
            s["position_aggressiveness"] = 1.0
            s["min_confidence_threshold"] = 0.45
            s["total_reviews"] = 0
            self_improve.save(s)
        except Exception as e:
            print(f"[BRAIN_REFRESH] self_improve: {e}")

        try:
            df = trader.get_bars(500)
            if df is not None and not df.empty:
                self._train_models(df, analyzer.analyze(df))
        except Exception as e:
            print(f"[BRAIN_REFRESH] yeniden egitim: {e}")

        try:
            tg.send(
                "🧠 <b>BEYINLER OTOMATIK YENILENDI</b>\n\n"
                "Ust uste zarar serisi algilandi. Stale dersler temizlendi, "
                "islem agresifligi ve guven esigi sifirlandi, AI model + 5 ajan "
                "birikmis tarama gecmisiyle yeniden egitildi."
            )
        except Exception:
            pass
        print("[BRAIN_REFRESH] Beyinler otomatik yenilendi.")

    def alisi_onayla(self):
        if self.bekleyen_alis:
            self._alisi_gerceklestir(self.bekleyen_alis)
        else:
            tg.send("Bekleyen alis yok.")

    def _alisi_gerceklestir(self, karar):
        try:
            size_pct = karar["execution"].get("size_percentage", 100)
            amount_usd = karar["execution"].get("amount_usd", None)
            result = executor.buy(size_pct, amount_usd=amount_usd)
            if result:
                db.save_trade("BUY", result["price"], result["qty"], 0, "AI sinyali", result["price"], result.get("mode", "SIM"))
                # Giriş maliyeti KOMİSYON DAHİL efektif fiyat olarak kaydedilir ki
                # scalp satış kontrolü komisyonu doğru hesaba katsın.
                quant_agent.state["son_giris_fiyati"] = executor._sim_entry if hasattr(executor, "_sim_entry") else result["price"]
                quant_agent.state["son_alis_zamani"] = time.time()
                quant_agent._save_state()
                self.bekleyen_alis = None
                self.bekleyen_satis = None
                self._son_alis_saati = time.time()
                is_sim = result.get("mode", "SIM") == "SIM"
                tag = "SIMULASYON " if is_sim else ""
                tutar_str = f"Tutar: ${amount_usd:.2f}" if amount_usd else f"Boyut: %{size_pct}"
                print(f"[BOT] {tag}ALIS: {result['qty']:.6f} BTC @ ${result['price']:,.2f} ({tutar_str})")
                tg.send_islem_sonucu("BUY", result["price"], result["qty"], yatirilan=result.get("cost"))
        except Exception as e:
            self.son_hata = f"ALIS: {str(e)[:100]}"
            print(f"[BOT] ALIS HATASI: {e}")
            tg.send(f"<b>ALIS HATASI</b>\n<code>{str(e)[:200]}</code>")

    def satisi_onayla(self):
        if self.bekleyen_satis:
            self._satisi_gerceklestir("Kullanici onayi")
        else:
            tg.send("Bekleyen satis yok.")

    def _satisi_gerceklestir(self, sebep):
        try:
            result = executor.sell()
            if result:
                pl = result.get("pl", 0)
                mode = result.get("mode", "SIM")
                quant_agent.islem_sonucu_kaydet(pl)
                db.save_trade("SELL", result["price"], result["qty"], pl, sebep, quant_agent.state.get("son_giris_fiyati", 0), mode)
                # --- GERİ BESLEME DÖNGÜSÜ ---
                # Zarar / stop-loss olan işlemlerde giriş koşulunu mini ders olarak kaydet.
                if pl < 0:
                    try:
                        from src import self_improve
                        entry = quant_agent.state.get("son_giris_teknik") or {}
                        cond = self_improve.describe_entry_condition(entry)
                        is_sl = "stop" in (sebep or "").lower() or "sl" in (sebep or "").lower()
                        reason_word = "Stop-loss" if is_sl else "Zararlı"
                        lesson = (f"{reason_word} işlem: [{cond}] ile AL yapıldı, terste kalındı. "
                                  f"Bu gösterge kombinasyonunda (özellikle aşırı şişmiş/aykırı bölgelerde) "
                                  f"tekrar AL sinyali üretme.")
                        self_improve.add_trade_lesson(lesson)
                        try:
                            tg.send("🧠 <b>OTONOM ÖĞRENME</b>\n\n" + lesson)
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"[SELF-IMPROVE] trade lesson hatasi: {e}")
                # Kapanan işlemi öğrenme döngüsüne bildir
                try:
                    n = self_improve.note_trade_closed()
                    if n >= 5:
                        lesson = self_improve.review_and_adapt(db, consensus)
                        if lesson:
                            print(f"[SELF-IMPROVE] {lesson}")
                            try:
                                tg.send("🧠 <b>OTONOM ÖĞRENME</b>\n\n" + lesson)
                            except Exception:
                                pass
                except Exception as e:
                    print(f"[SELF-IMPROVE] hata: {e}")
                self.bekleyen_alis = None
                self.bekleyen_satis = None
                quant_agent.state["son_sl"] = 0
                quant_agent.state["son_tp"] = 0
                quant_agent._save_state()
                self._son_alis_saati = 0
                is_sim = mode == "SIM"
                tag = "SIMULASYON " if is_sim else ""
                print(f"[BOT] {tag}SATIS: K/Z ${pl:+,.2f} ({sebep})")
                tg.send_islem_sonucu("SELL", result["price"], result["qty"], pl, yatirilan=result.get("cost"))
        except Exception as e:
            self.son_hata = f"SATIS: {str(e)[:100]}"
            print(f"[BOT] SATIS HATASI: {e}")
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
                pnl_str = f"K/Z: ${t['pnl']:+,.2f}" if t.get('pnl') else ""
                lines.append(
                    f"{emoji} {t['action']} ${t['price']:,.2f} | {pnl_str}"
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
            "<code>/son</code> - Son islemler\n"
            "<code>/miktar 100</code> - Miktar ayarla\n"
            "<code>/artir 50</code> - Miktar artir\n"
            "<code>/azalt 25</code> - Miktar azalt\n"
            "<code>/durdur</code> - Taramayi duraklat\n"
            "<code>/devam</code> - Taramaya devam"
        )
        tg.send(msg)

    def cmd_durdur(self):
        self.paused = True
        tg.send("⏸ Tarama duraklatildi. <code>/devam</code> ile devam et.")

    def cmd_devam(self):
        self.paused = False
        tg.send("▶ Tarama devam ediyor.")

    def reset_everything(self):
        """Simülasyonu BAŞTAN SONA sıfırlar: tüm veriler, istatistikler,
        öğrenilen dersler ve simüle edilmiş bakiye. Binance'e hiç dokunmaz."""
        # 1. Tüm veritabanı kayıtlarını temizle (yerel + supabase)
        try:
            db.reset_all()
        except Exception as e:
            print(f"[RESET] db reset hatasi: {e}")

        # 2. Ajan istatistiklerini sıfırla
        for k in ("toplam_islem", "kazanma", "kaybetme", "ardisik_kayip",
                  "son_islem_kar_zarar", "son_giris_fiyati", "son_sl", "son_tp",
                  "consecutive_wins", "free_cash"):
            if k in quant_agent.state:
                quant_agent.state[k] = 0 if k != "free_cash" else 0.0
        quant_agent.state["active_pool_size"] = 1000.0
        quant_agent._save_state()

        # 3. Konsensüs koordinatör sayaclarını sıfırla
        consensus.total_decisions = 0
        consensus.consensus_reached = 0

        # 4. Ayarlar sifirlancak AMA dersler korunur (kullanici: dersler silinmesin)
        try:
            from src import self_improve
            s = self_improve.load()
            s["position_aggressiveness"] = 1.0
            s["total_reviews"] = 0
            s["trades_since_review"] = 0
            self_improve.save(s)
        except Exception as e:
            print(f"[RESET] self_improve reset hatasi: {e}")

        # 5. Simülasyon bakiyesini başlangıç değerine çek
        try:
            executor.reset_sim()
        except Exception as e:
            print(f"[RESET] executor reset hatasi: {e}")

        self.last_action = None
        self.last_gemini_debate = None
        print("[RESET] Simülasyon baştan sona sıfırlandı.")
        return True

    def get_status(self):
        try:
            acc = executor.get_account()
            pos = executor.get_position()
            state = quant_agent.get_state()
            ai_state = ai_model.get_state()
            return {
                "running": self.running,
                "paused": self.paused,
                "auto_trade": True,
                "total_scans": self.total_scans,
                "last_scan": self.last_scan,
                "portfolio_value": acc.get("portfolio_value", 0),
                "cash": acc.get("cash", 0),
                "pozisyon_durumu": "Aktif" if pos else "Yok",
                "kar_zarar": db.get_stats().get("toplam_kar_zarar", 0) + (pos["unrealized_pl"] if pos else 0),
                "son_karar": self.last_action,
                "toplam_islem": state.get("toplam_islem", 0),
                "kazanma": state.get("kazanma", 0),
                "kaybetme": state.get("kaybetme", 0),
                "son_hata": self.son_hata,
                "son_fiyat": trader.get_price() if self.running else 0,
                "ai_accuracy": ai_state.get("accuracy", 0),
                "ai_prediction_count": ai_state.get("prediction_count", 0),
                "ai_trained": ai_state.get("is_trained", False),
                "ai_memory_size": ai_state.get("memory_size", 0),
                "executor_mode": settings.executor_mode,
                "sim_balance": executor._sim_balance if hasattr(executor, '_sim_balance') else 0,
                "gemini_active": bool(settings.llm_api_key),
                "gemini_last_decision": self.last_gemini_debate.get("final_decision", "---") if self.last_gemini_debate else "---",
                "daily_goal_pct": settings.daily_goal_pct,
                "aggressive_mode": settings.aggressive_mode,
                "symbol": settings.symbol,
                "quote_asset": settings.quote_asset,
                "usd_try": trader.get_usd_try_rate(),
                "commission_rate": settings.commission_rate,
                "total_commission": db.total_commission(),
            }
        except Exception as e:
            return {"running": self.running, "error": str(e), "son_hata": self.son_hata}


bot = Bot()


def setup_telegram():
    tg.on_start(lambda: bot.start())
    tg.on_stop(lambda: bot.stop())
    tg.on_scan(lambda: bot.scan())
    tg.on_status(lambda: tg.send_durum(bot.get_status()))
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
    tg.start_polling()
