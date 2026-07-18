import json
import os
import numpy as np
from datetime import datetime
from src.config import settings
from src.ai_model import ai_model
from src.strategy import signal_strategy
from src import supabase_store
from src.agents import consensus


class QuantAgent:
    def __init__(self):
        self.state_file = settings.memory_file
        self.state = self._load_state()
        self._trade_history = []
        # Ajan durumlarını yükle
        self._load_agent_states()

    def _load_agent_states(self):
        """Konsensüs ajan durumlarını Supabase'den yükle."""
        try:
            agent_data = supabase_store.load_consensus_states()
            if agent_data:
                consensus.load_states(agent_data)
        except Exception as e:
            print(f"[QUANT_AGENT] Ajan durumlari yuklenemedi: {e}")

    def _save_agent_states(self):
        """Konsensüs ajan durumlarını Supabase'e kaydet."""
        try:
            data = consensus.save_states()
            supabase_store.save_consensus_states(data)
        except Exception as e:
            print(f"[QUANT_AGENT] Ajan durumlari kaydedilemedi: {e}")

    def _load_state(self):
        local_state = None
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    local_state = json.load(f)
            except:
                pass
        
        if not local_state:
            sb_state = supabase_store.load_agent_state()
            if sb_state:
                print("[QUANT_AGENT] Agent state Supabase'den yuklendi.")
                try:
                    with open(self.state_file, "w") as f:
                        json.dump(sb_state, f, indent=2, default=str)
                except:
                    pass
                local_state = sb_state

        if local_state:
            # Eksik sermaye yönetimi alanlarını enjekte et (Geriye Dönük Uyumluluk)
            if "free_cash" not in local_state:
                local_state["free_cash"] = 0.0
            if "consecutive_wins" not in local_state:
                local_state["consecutive_wins"] = 0
            if "active_pool_size" not in local_state:
                local_state["active_pool_size"] = 1000.0
            return local_state
            
        return {
            "son_islem_kar_zarar": 0.0,
            "son_hatalar": [],
            "aktif_strateji_notu": "",
            "risk_seviyesi_ayari": "normal",
            "ardisik_kayip": 0,
            "consecutive_wins": 0,
            "free_cash": 0.0,
            "active_pool_size": 1000.0,
            "son_sinyal": None,
            "toplam_islem": 0,
            "kazanma": 0,
            "kaybetme": 0,
            "weights": {
                "rsi": 1.0, "macd": 1.0, "ema": 1.0,
                "bb": 1.0, "vol": 1.0, "breakout": 1.0,
                "orderbook": 1.0, "haber": 1.0, "momentum": 1.0
            },
            "weight_hits": {k: 0 for k in ["rsi","macd","ema","bb","vol","breakout","orderbook","haber","momentum"]},
            "weight_misses": {k: 0 for k in ["rsi","macd","ema","bb","vol","breakout","orderbook","haber","momentum"]},
        }

    def _save_state(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            print(f"[QUANT_AGENT] Local state kaydetme hatasi: {e}")
            
        try:
            supabase_store.save_agent_state(self.state)
        except Exception as e:
            print(f"[QUANT_AGENT] Supabase state kaydetme hatasi: {e}")

    def calculate_order_size(self, price, support, resistance):
        """
        Dinamik Emir Büyüklüğü Fonksiyonu (Order Size Scaling)
        Anlık fiyat, destek/direnç noktaları ve serbest nakdi girdi olarak alıp
        ideal alım/satım miktarını (size_usd) hesaplar.
        """
        free_cash = self.state.get("free_cash", 0.0)
        active_pool = self.state.get("active_pool_size", 1000.0)

        # Fiyatın destek/direnç aralığındaki yeri (0 = Destek, 1 = Direnç)
        if resistance > support:
            range_pos = (price - support) / (resistance - support)
        else:
            range_pos = 0.5
            
        range_pos = max(0.0, min(1.0, range_pos))
        
        # 1. Kural: Emir büyüklüğü fiyatın destek/direnç konumuna göre esnesin
        # Fiyat desteğe yaklaştıkça çarpan artar (1.5x'e kadar). Dirençteyse çarpan küçülür (0.2x).
        price_multiplier = 1.5 - 1.3 * range_pos
        
        # Fiyat direnç sınırındaysa (%90+), alımı tamamen durdur
        if range_pos > 0.90:
            price_multiplier = 0.0
            
        # 4. Kural: Grid/Kademe koruması (Kilitlenmeyi önlemek için havuzu 3 parçaya böl)
        max_parts = 3
        base_grid_size = active_pool / max_parts
        
        # Emir büyüklüğü hesaplama
        order_size = base_grid_size * price_multiplier
        
        # 2. Kural: Serbest nakit kullanımı (Dip Avcılığı)
        # Fiyat desteğe çok yakın veya altındaysa (derin düşüş), serbest nakdin %30'unu cephane olarak ekle
        dip_budget = 0.0
        if range_pos < 0.15 and free_cash > 5.0:
            dip_budget = min(free_cash * 0.30, 300.0) # Serbest nakdin %30'unu veya maks 300$ kullan
            order_size += dip_budget
            
        # Havuz ve serbest nakit limitlerini aşmamalı
        order_size = min(order_size, active_pool + free_cash)
        order_size = max(0.0, order_size)
        
        # Loglama
        print(f"[CAPITAL_MGMT] Fiyat: ${price:,.2f} | Destek: ${support:,.2f} | Direnc: ${resistance:,.2f} | Range Pos: %{range_pos*100:.1f}")
        print(f"[CAPITAL_MGMT] Aktif Havuz: ${active_pool:.2f} | Serbest Nakit: ${free_cash:.2f}")
        print(f"[CAPITAL_MGMT] Hesaplanan Siparis Boyutu: ${order_size:.2f} (Baz Grid: ${base_grid_size:.2f}, Carpan: {price_multiplier:.2f}x, Dip Katkısı: ${dip_budget:.2f})")
        
        return round(order_size, 2)

    def analyze(self, teknik_analiz, internet_ve_haberler, mevcut_portfoy, gecmis_hafiza, gemini_debate=None):
        hata_var = False
        system_log = ""

        if teknik_analiz is None or "price" not in teknik_analiz:
            system_log = "HATA: Teknik analiz verisi eksik"
            return self._hold_karar("normal", "", system_log)

        fiyat = teknik_analiz["price"]
        rsi = teknik_analiz["rsi"]
        ema_cross = teknik_analiz["ema_cross"]
        ema_dist = teknik_analiz.get("ema_dist", 0)
        macd_hist = teknik_analiz["macd_hist"]
        macd_hist_prev = teknik_analiz["macd_hist_prev"]
        vol_ratio = teknik_analiz["vol_ratio"]
        bb_pct = teknik_analiz["bb_pct"]
        atr = teknik_analiz["atr"]
        breakout_up = teknik_analiz.get("breakout_up", 0)
        breakout_down = teknik_analiz.get("breakout_down", 0)
        price_change_5 = teknik_analiz.get("price_change_5", 0)

        acik_pozisyon = mevcut_portfoy.get("acik_pozisyon", False)
        giris_fiyati = mevcut_portfoy.get("giris_fiyati", 0)
        usdt_bakiye = mevcut_portfoy.get("usdt_bakiye", 0)
        btc_bakiye = mevcut_portfoy.get("btc_bakiye", 0)

        ardisik_kayip = self.state.get("ardisik_kayip", 0)
        risk_seviyesi = self.state.get("risk_seviyesi_ayari", "normal")

        # ─── XGBoost AI Tahmini ───
        ai_prob, ai_conf = ai_model.predict(teknik_analiz)

        # ─── Strict Strateji Sinyali (hızlı giriş/çıkış) ───
        signal = signal_strategy.analyze(teknik_analiz)
        if signal.get("strict_signal") and signal["action"] in ("BUY", "SELL"):
            if signal["action"] == "BUY" and ai_prob >= 0.4 and not acik_pozisyon:
                support = teknik_analiz.get("support", fiyat * 0.95)
                resistance = teknik_analiz.get("resistance", fiyat * 1.05)
                order_size_usd = self.calculate_order_size(fiyat, support, resistance)
                if order_size_usd <= 10.0:
                    return self._hold_karar(risk_seviyesi, "Strict BUY iptal: Dirençe çok yakın veya bütçe yetersiz", "STRICT_BUY_SHRUNK")

                self.state["son_sinyal"] = {"action": "BUY", "source": "STRICT", "ai_prob": ai_prob}
                self._save_state()
                return {
                    "action": "BUY",
                    "confidence_score": round(max(ai_prob, 0.7), 2),
                    "execution": {
                        "size_percentage": 100,
                        "amount_usd": order_size_usd,
                        "stop_loss": signal.get("stop_loss", 0),
                        "take_profit": signal.get("target_profit", 0),
                    },
                    "memory_update": {
                        "aktif_strateji_notu": signal["reason"],
                        "risk_seviyesi_ayari": risk_seviyesi,
                    },
                    "system_log": f"STRICT+AI:{ai_prob:.0%}|Size:${order_size_usd:.2f}"
                }
            if signal["action"] == "SELL" and ai_prob <= 0.6 and acik_pozisyon:
                giris = mevcut_portfoy.get("giris_fiyati", 0) or self.state.get("son_giris_fiyati", 0)
                if self._should_hold_for_commission(fiyat, giris):
                    return self._hold_karar(risk_seviyesi, "Komisyon korumasi: yetersiz hareket", "COMMISSION_HOLD")
                self.state["son_sinyal"] = {"action": "SELL", "source": "STRICT", "ai_prob": ai_prob}
                self._save_state()
                return {
                    "action": "SELL",
                    "confidence_score": round(max(1 - ai_prob, 0.7), 2),
                    "execution": {
                        "size_percentage": 100,
                        "stop_loss": 0,
                        "take_profit": 0,
                    },
                    "memory_update": {
                        "aktif_strateji_notu": signal["reason"],
                        "risk_seviyesi_ayari": risk_seviyesi,
                    },
                    "system_log": f"STRICT+AI:{ai_prob:.0%}"
                }

        # ─── 5 AI AJAN KONSENSÜS SİSTEMİ ───
        consensus_result = consensus.vote(teknik_analiz, internet_ve_haberler, gemini=gemini_debate)
        consensus_action = consensus_result["action"]
        consensus_confidence = consensus_result["confidence"]
        consensus_ok = consensus_result["consensus"]
        votes = consensus_result["votes"]
        details = consensus_result["details"]

        details_clean = details.replace("🟢", "[BUY]").replace("🔴", "[SELL]").replace("⚪", "[HOLD]")
        print(f"  [CONSENSUS] {details_clean}")
        print(f"  [CONSENSUS] Karar: {consensus_action} | Güven: {consensus_confidence:.0%} | Konsensüs: {'EVET' if consensus_ok else 'HAYIR'}")
        print(f"  [CONSENSUS] AL:{consensus_result['buy_count']} SAT:{consensus_result['sell_count']} BEKLE:{consensus_result['hold_count']}")

        # ─── GEMINI 5-BEYIN TARTIŞMA KARARI (ekrandaki 5 ajansın gerçek kararı) ───
        # Kullanıcının izlediği bu 5 ajan (Trend Avcısı / Matematikçi / Balina İzleyici /
        # Risk Yöneticisi / Hakem) güçlü ve çoğunlukla aynı yönde karar verirse ARTIL
        # doğrudan tetiklenir. Böylece ekranda "5 AL" görünüyorsa sistem de işlem yapar.
        debate_action = "HOLD"
        debate_conf = 0.0
        debate_buy = 0
        debate_sell = 0
        debate_votes = {}
        if gemini_debate:
            debate_action = gemini_debate.get("final_decision", "HOLD")
            try:
                debate_conf = float(gemini_debate.get("final_confidence", 0) or 0)
            except Exception:
                debate_conf = 0.0
            for b in gemini_debate.get("brains", []):
                v = b.get("vote") or "HOLD"
                debate_votes[b.get("ajan", "?")] = v
                if v == "BUY":
                    debate_buy += 1
                elif v == "SELL":
                    debate_sell += 1
        # Güçlü sinyal: final yön + güven >= %50 + en az 3/5 ajan aynı yönde
        # (test/izleme kolaylığı için eşik 0.60 -> 0.50 düşürüldü; istenirse yükseltilebilir)
        debate_strong_buy = debate_action == "BUY" and debate_conf >= 0.50 and debate_buy >= 3
        debate_strong_sell = debate_action == "SELL" and debate_conf >= 0.50 and debate_sell >= 3
        if debate_strong_buy or debate_strong_sell:
            print(f"  [DEBATE] final={debate_action} guven={debate_conf:.0%} | AL:{debate_buy} SAT:{debate_sell} (GÜÇLÜ SİNYAL)")

        # Ardışık kayıp durumunda güven eşiğini yükselt
        min_confidence = 0.45
        if ardisik_kayip >= settings.max_consecutive_losses:
            min_confidence = 0.60
            risk_seviyesi = "muhafazakar"

        # ─── Konsensüs sonucunu XGBoost ile doğrula ───
        used_indicators = []
        for name, v in votes.items():
            if v["action"] != "HOLD":
                used_indicators.append(name)

        # Konsensüs + AI Birleşik Karar  (VEYA güçlü 5-ajan tartışması)
        if (consensus_ok and consensus_action == "BUY" and not acik_pozisyon) or (debate_strong_buy and not acik_pozisyon):
            # Güven birleştirme: tartışma kararı mı, konsensüs mü?
            if debate_strong_buy and not (consensus_ok and consensus_action == "BUY"):
                combined_confidence = debate_conf
                src = "GEMINI_DEBATE"
            else:
                combined_confidence = consensus_confidence * 0.50 + ai_prob * 0.30 + (signal.get("long_score", 0) / 5 * 0.20)
                combined_confidence = max(combined_confidence, consensus_confidence * 0.7)
                src = "CONSENSUS"

            # AI veto kontrolü (yalnızca konsensüs kaynağı için; tartışma kararına saygı duyulur)
            if src == "CONSENSUS" and ai_prob < 0.35 and ai_conf > 0.3:
                system_log = f"CONSENSUS_BUY_VETOED|AI:{ai_prob:.0%}|{details}"
                print(f"  [VETO] Konsensüs AL dedi ama XGBoost düşüş öngörüyor ({ai_prob:.0%})")
                return self._hold_karar(risk_seviyesi, "AI Veto", system_log)

            if src == "GEMINI_DEBATE" or combined_confidence >= min_confidence:
                sl_price, tp_price = self._scalp_sl_tp(fiyat, atr)
                
                # Dynamic order size
                support = teknik_analiz.get("support", fiyat * 0.95)
                resistance = teknik_analiz.get("resistance", fiyat * 1.05)
                order_size_usd = self.calculate_order_size(fiyat, support, resistance)
                if order_size_usd <= 10.0:
                    return self._hold_karar(risk_seviyesi, "Consensus BUY iptal: Dirençe çok yakın veya bütçe yetersiz", "CONSENSUS_BUY_SHRUNK")

                self.state["son_sinyal"] = {
                    "action": "BUY",
                    "price": fiyat,
                    "time": datetime.now().isoformat(),
                    "indicators": used_indicators,
                    "consensus_votes": {k: v["action"] for k, v in votes.items()},
                    "debate_votes": debate_votes,
                    "buy_score": consensus_result["buy_score"],
                    "sell_score": consensus_result["sell_score"],
                    "rsi": rsi,
                }

                system_log = f"{src}_BUY|ML:{consensus_result['buy_count']}/5|Debate:{debate_buy}AL/{debate_sell}SAT|AI:{ai_prob:.0%}|Size:${order_size_usd:.2f}|{details}"

                memory_update = {
                    "aktif_strateji_notu": f"ALIS ({src}): {consensus_result['buy_count']}/5 konsensüs, {debate_buy}/5 tartışma onayladı",
                    "risk_seviyesi_ayari": risk_seviyesi
                }

                self._save_state()
                self._save_agent_states()

                return {
                    "action": "BUY",
                    "confidence_score": round(combined_confidence, 2),
                    "execution": {
                        "size_percentage": 100,
                        "amount_usd": order_size_usd,
                        "stop_loss": sl_price,
                        "take_profit": tp_price,
                    },
                    "memory_update": memory_update,
                    "system_log": system_log
                }

        elif (consensus_ok and consensus_action == "SELL" and acik_pozisyon) or (debate_strong_sell and acik_pozisyon):
            mevcut_kar = (fiyat - giris_fiyati) / giris_fiyati * 100 if giris_fiyati > 0 else 0
            if debate_strong_sell and not (consensus_ok and consensus_action == "SELL"):
                combined_confidence = debate_conf
                src = "GEMINI_DEBATE"
            else:
                combined_confidence = consensus_confidence * 0.50 + (1 - ai_prob) * 0.30 + (signal.get("short_score", 0) / 5 * 0.20)
                combined_confidence = max(combined_confidence, consensus_confidence * 0.7)
                src = "CONSENSUS"

            # AI veto kontrolü (yalnızca konsensüs kaynağı için; tartışma kararına saygı duyulur)
            if src == "CONSENSUS" and ai_prob > 0.65 and ai_conf > 0.3:
                system_log = f"CONSENSUS_SELL_VETOED|AI:{ai_prob:.0%}|{details}"
                print(f"  [VETO] Konsensüs SAT dedi ama XGBoost yükseliş öngörüyor ({ai_prob:.0%})")
                return self._hold_karar(risk_seviyesi, "AI Veto (Yükseliş)", system_log)

            if src == "GEMINI_DEBATE" or combined_confidence >= min_confidence:
                # KOMISYON KORUMASI: yeterli hareket yoksa SAT yapma
                if self._should_hold_for_commission(fiyat, giris_fiyati):
                    return self._hold_karar(risk_seviyesi, "Komisyon korumasi: yetersiz hareket", "COMMISSION_HOLD")
                self.state["son_sinyal"] = {
                    "action": "SELL",
                    "price": fiyat,
                    "time": datetime.now().isoformat(),
                    "indicators": used_indicators,
                    "consensus_votes": {k: v["action"] for k, v in votes.items()},
                    "debate_votes": debate_votes,
                    "buy_score": consensus_result["buy_score"],
                    "sell_score": consensus_result["sell_score"],
                }

                system_log = f"{src}_SELL|ML:{consensus_result['sell_count']}/5|Debate:{debate_buy}AL/{debate_sell}SAT|AI:{ai_prob:.0%}|{details}"

                memory_update = {
                    "aktif_strateji_notu": (f"SATIS ({src}): {consensus_result['sell_count']}/5 konsensüs, {debate_sell}/5 tartışma (Kar: %{mevcut_kar:+.2f})"
                                            if abs(mevcut_kar) > 0 else
                                            f"SATIS ({src}): {consensus_result['sell_count']}/5 konsensüs, {debate_sell}/5 tartışma"),
                    "risk_seviyesi_ayari": risk_seviyesi
                }

                self._save_state()
                self._save_agent_states()

                return {
                    "action": "SELL",
                    "confidence_score": round(combined_confidence, 2),
                    "execution": {
                        "size_percentage": 100,
                        "stop_loss": 0,
                        "take_profit": 0,
                    },
                    "memory_update": memory_update,
                    "system_log": system_log
                }

        # ─── SCALPING HIZLI YOL (M10/M30 mikro hacim kırılımı) ───
        # Konsensüs/AI beklenmeden, kısa vadeli mikro trend + hacim kırılımına
        # göre hızlı gir-çık ("Vur-Kaç") yapar. Tamamen kural tabanlıdır; ML
        # eğitimi veya Gemini anahtarı GEREKTİRMEZ, böylece bot her zaman
        # scalping fırsatı bulabilir.
        scalp_action = self._scalp_signal(teknik_analiz, acik_pozisyon, ai_prob,
                                          self.state.get("son_alis_zamani", 0))
        if scalp_action == "BUY" and not acik_pozisyon:
            sl_price, tp_price = self._scalp_sl_tp(fiyat, atr)
            support = teknik_analiz.get("support", fiyat * 0.99)
            resistance = teknik_analiz.get("resistance", fiyat * 1.01)
            order_size_usd = self.calculate_order_size(fiyat, support, resistance)
            if order_size_usd <= 10.0:
                system_log = "SCALP BUY iptal: bütçe/direnç yetersiz"
                print(f"  [SCALP] {system_log}")
            else:
                self.state["son_sinyal"] = {"action": "BUY", "source": "SCALP", "ai_prob": ai_prob}
                self._save_state()
                print(f"  [SCALP] MIKRO KIRILIM AL (AI:{ai_prob:.0%}) | Size:${order_size_usd:.2f} SL:${sl_price} TP:${tp_price}")
                return {
                    "action": "BUY",
                    "confidence_score": round(max(ai_prob, 0.6), 2),
                    "execution": {
                        "size_percentage": 100,
                        "amount_usd": order_size_usd,
                        "stop_loss": sl_price,
                        "take_profit": tp_price,
                    },
                    "memory_update": {
                        "aktif_strateji_notu": "SCALP: M10/M30 mikro kırılım + hacim patlaması",
                        "risk_seviyesi_ayari": risk_seviyesi,
                    },
                    "system_log": f"SCALP_BUY|{details}",
                }
        elif scalp_action == "SELL" and acik_pozisyon:
            self.state["son_sinyal"] = {"action": "SELL", "source": "SCALP", "ai_prob": ai_prob}
            self._save_state()
            print(f"  [SCALP] MIKRO KIRILIM SAT (AI:{ai_prob:.0%})")
            return {
                "action": "SELL",
                "confidence_score": round(max(1 - ai_prob, 0.6), 2),
                "execution": {"size_percentage": 100, "stop_loss": 0, "take_profit": 0},
                "memory_update": {
                    "aktif_strateji_notu": "SCALP: M10/M30 mikro kırılım tersi",
                    "risk_seviyesi_ayari": risk_seviyesi,
                },
                "system_log": f"SCALP_SELL|{details}",
            }

        # Konsensüs sağlanamadı → HOLD
        system_log = (f"NO_TRADE|ML AL:{consensus_result['buy_count']} SAT:{consensus_result['sell_count']} "
                      f"|Debate:{debate_action}(%{debate_conf*100:.0f}) AL:{debate_buy} SAT:{debate_sell}"
                      f"|{details}")
        return self._hold_karar(risk_seviyesi, "Konsensüs yok", system_log)

    def _scalp_sl_tp(self, fiyat, atr):
        """
        Kısa vadeli (M10/M30) scalping için DİNAMİK stop-loss / take-profit.
        SL ve TP, ATR'a göre ölçeklenir ama ayarlanabilir maksimum yüzde
        cap'iyle sınırlanır; böylece dar aralıklı "Vur-Kaç" hedefi korunur.
        """
        sl_atr = fiyat - settings.scalp_sl_atr_mult * atr if atr and atr > 0 else float("-inf")
        tp_atr = fiyat + settings.scalp_tp_atr_mult * atr if atr and atr > 0 else float("inf")
        sl_cap = fiyat * (1 - settings.scalp_max_sl_pct / 100.0)
        tp_cap = fiyat * (1 + settings.scalp_max_tp_pct / 100.0)

        # Stop-loss: iki yöntemden DAHA YAKIN (daha az riskli) olanı seçilir.
        sl_price = max(sl_atr, sl_cap)
        # Take-profit: iki yöntemden DAHA YAKIN (daha hızlı realize) olanı seçilir.
        tp_price = min(tp_atr, tp_cap)

        # Pozitif R:R garantisi (TP her zaman SL'den uzakta kalsın).
        if tp_price <= sl_price:
            tp_price = round(fiyat * 1.004, 2)

        return round(sl_price, 2), round(tp_price, 2)

    def _scalp_signal(self, t, acik_pozisyon, ai_prob, giris_zamani=0):
        """
        Çoklu indikatör onayli AL/SAT sinyali.
        Gercek borsada her islem KOMISYON (maker %0.1 + spread + slippage) demek.
        Bu yuzden TEK indikator yerine en az 3 bagimsiz filtrenin (EMA trend +
        RSI bolgesi + MACD yonu + hacim + kirilim) uyumlu olmasi sart.
        Boylece "alip direk sat" dongusu kirilir, islem sayisi azalir,
        her islem komisyonu karsilar.
        Donus: "BUY" | "SELL" | "HOLD"
        """
        base_ema = t.get("ema_cross")
        m5_ema = t.get("5m_ema_cross", base_ema)
        m10_ema = t.get("10m_ema_cross", base_ema)
        m15_ema = t.get("15m_ema_cross", base_ema)
        m30_ema = t.get("30m_ema_cross", base_ema)
        rsi = t.get("rsi", 50)
        m5_rsi = t.get("5m_rsi", rsi)
        m10_rsi = t.get("10m_rsi", rsi)
        m15_rsi = t.get("15m_rsi", rsi)
        m30_rsi = t.get("15m_rsi", rsi)
        macd_hist = t.get("macd_hist", 0)
        m5_macd = t.get("5m_macd_hist", macd_hist)
        m10_macd = t.get("10m_macd_hist", macd_hist)
        vol = t.get("vol_ratio", 1.0)
        pchg5 = t.get("price_change_5", 0)
        bb_pct = t.get("bb_pct", 0.5)

        tf_emas = [base_ema, m5_ema, m10_ema, m15_ema, m30_ema]
        bull_count = sum(1 for e in tf_emas if e == "bullish")
        bear_count = sum(1 for e in tf_emas if e == "bearish")

        brk_up = (t.get("breakout_up", 0) or t.get("5m_breakout_up", 0)
                  or t.get("10m_breakout_up", 0) or t.get("15m_breakout_up", 0)
                  or t.get("30m_breakout_up", 0))
        brk_dn = (t.get("breakout_down", 0) or t.get("5m_breakout_down", 0)
                  or t.get("10m_breakout_down", 0) or t.get("15m_breakout_down", 0)
                  or t.get("30m_breakout_down", 0))

        # ─── ORTAK FILTRELER (her biri bagimsiz bir sinyal) ───
        # F1: Coklu periyot EMA trendi (en az 2 periyot ayni yonde)
        # F2: RSI makul bolgede (asiri alim/satim degil)
        # F3: MACD histogrami yonu (momentum)
        # F4: Hacim patlamasi (vol_ratio > 1.1)
        # F5: Kirilim (breakout_up/down) VEYA guclu ivme (pchg5)

        def _bull_filters():
            f = []
            f.append(bull_count >= 2)                          # F1
            f.append(35 < rsi < 72)                            # F2
            f.append(macd_hist > 0 or m5_macd > 0)             # F3
            f.append(vol > 1.05)                               # F4
            f.append(bool(brk_up) or pchg5 > 0.2)              # F5
            return f

        def _bear_filters():
            f = []
            f.append(bear_count >= 2)                          # F1
            f.append(28 < rsi < 65)                            # F2
            f.append(macd_hist < 0 or m5_macd < 0)             # F3
            f.append(vol > 1.05)                               # F4
            f.append(bool(brk_dn) or pchg5 < -0.2)             # F5
            return f

        if not acik_pozisyon:
            fb = _bull_filters()
            # En az 3 filtre uyumlu olmali (tek indikator YETMEZ)
            if sum(fb) >= 3:
                return "BUY"
        else:
            fs = _bear_filters()
            # Satista da en az 3 filtre (konsensuz "hoparlör" satis engellenir)
            # + DINAMIK KOMISYON KORUMASI (sistem kendi ogrenir, sabit degil)
            import time as _t
            gecen = (_t.time() - giris_zamani) if giris_zamani else 9999
            MIN_HOLD_SN = settings.scalp_min_hold_sec
            if sum(fs) >= 3 and gecen >= MIN_HOLD_SN:
                giris_fiyati = self.state.get("son_giris_fiyati", 0) or t.get("price", 0)
                if not self._should_hold_for_commission(t.get("price", 0), giris_fiyati):
                    return "SELL"
        return "HOLD"

    def _should_hold_for_commission(self, fiyat, giris_fiyati):
        """KOMISYON KORUMASI (dinamik, sistem ogrenir).
        Sistem kendi hesapladigi min_exit_move_pct kadar fiyat hareketi
        OLMADAN pozisyonu kapatmaz. Boylece her islem komisyonu karsilanir.
        Döner: True ise (henuz yeterli hareket yok) SAT YAPMA, HOLD et.
        """
        if not giris_fiyati or giris_fiyati <= 0 or not fiyat or fiyat <= 0:
            return False  # bilinmiyorsa engelleme (guvenli taraf)
        from src import self_improve
        min_move = self_improve.compute_min_exit_move()  # %
        hareket = abs(fiyat - giris_fiyati) / giris_fiyati * 100
        if hareket < min_move:
            print(f"  [KOMISYON] SAT engellendi: hareket %{hareket:.2f} < min_exit %{min_move:.2f} (komisyon korumasi)")
            return True
        return False


        return {
            "action": "HOLD",
            "confidence_score": 0.0,
            "execution": {
                "size_percentage": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
            },
            "memory_update": {
                "aktif_strateji_notu": strateji_notu,
                "risk_seviyesi_ayari": risk_seviyesi,
            },
            "system_log": system_log
        }

    def islem_sonucu_kaydet(self, kar_zarar):
        self.state["toplam_islem"] += 1
        self.state["son_islem_kar_zarar"] = round(kar_zarar, 4)
        
        # Kar/Zarar durumuna gore ardisik galibiyet ve maglubiyetleri hesapla
        if kar_zarar > 0:
            self.state["kazanma"] += 1
            self.state["consecutive_wins"] = self.state.get("consecutive_wins", 0) + 1
            self.state["ardisik_kayip"] = 0
            
            # Kar realizasyonu ve Serbest Nakit ayirma (%30 kar stashing)
            hoard_pct = 0.30
            hoarded = round(kar_zarar * hoard_pct, 2)
            self.state["free_cash"] = round(self.state.get("free_cash", 0.0) + hoarded, 2)
            print(f"[CASH_HOARDING] Karlı islem! Kar: ${kar_zarar:.2f} | Serbest Nakde aktarılan (%30): ${hoarded:.2f} | Toplam Serbest Nakit: ${self.state['free_cash']:.2f}")
        elif kar_zarar < 0:
            self.state["kaybetme"] += 1
            self.state["ardisik_kayip"] = self.state.get("ardisik_kayip", 0) + 1
            self.state["consecutive_wins"] = 0
            print(f"[CASH_HOARDING] Zararlı islem! Zarar: ${kar_zarar:.2f} | Ardisik Kayip: {self.state['ardisik_kayip']}")
        else:
            pass

        # Esnek Butce ve Havuz Olcekleme (Pool Scaling)
        # Baslangic/Baz havuz boyutu 1000$
        # Win-streak durumunda butceyi esnet (Maksimum 2000$)
        # Lose-streak durumunda butceyi kis (Minimum 500$)
        base_pool = 1000.0
        wins = self.state.get("consecutive_wins", 0)
        losses = self.state.get("ardisik_kayip", 0)

        if wins >= 2:
            new_pool = min(2000.0, base_pool + (wins - 1) * 250.0)
            self.state["active_pool_size"] = round(new_pool, 2)
            print(f"[POOL_SCALING] Basarılı trend! Havuz esnetildi: ${self.state['active_pool_size']:.2f} (Ardisik Galibiyet: {wins})")
        elif losses >= 2:
            new_pool = max(500.0, base_pool - losses * 200.0)
            self.state["active_pool_size"] = round(new_pool, 2)
            print(f"[POOL_SCALING] Riskli piyasa! Havuz kucultuldu: ${self.state['active_pool_size']:.2f} (Ardisik Kayip: {losses})")
        else:
            # Stabil/normal durum
            self.state["active_pool_size"] = base_pool
            print(f"[POOL_SCALING] Havuz stabil seviyede: ${self.state['active_pool_size']:.2f}")

        # Konsensus ajanlarına sonucu bildir
        son_sinyal = self.state.get("son_sinyal", {})
        predicted_action = son_sinyal.get("action", "HOLD")
        actual_profitable = kar_zarar > 0
        consensus.record_result_all(predicted_action, actual_profitable)

        # Eski agırlık sistemi de guncelle (geriye uyumluluk)
        indicators = son_sinyal.get("indicators", [])
        if indicators:
            hits = self.state["weight_hits"]
            misses = self.state["weight_misses"]
            for ind in indicators:
                if kar_zarar > 0:
                    hits[ind] = hits.get(ind, 0) + 1
                else:
                    misses[ind] = misses.get(ind, 0) + 1

            w = self.state["weights"]
            for ind in indicators:
                total = hits.get(ind, 0) + misses.get(ind, 0)
                if total >= 3:
                    accuracy = hits.get(ind, 0) / total
                    if accuracy > 0.6:
                        w[ind] = min(1.5, w[ind] * 1.1)
                    elif accuracy < 0.3:
                        w[ind] = max(0.5, w[ind] * 0.9)
            self.state["weights"] = w

        self._save_state()
        self._save_agent_states()

    def get_state(self):
        return self.state

    def get_consensus_state(self):
        """Panel'de göstermek için konsensüs durumunu döndür."""
        return consensus.get_all_states()


quant_agent = QuantAgent()