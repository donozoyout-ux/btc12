import json
import os
import time
try:
    import ccxt
except Exception:
    ccxt = None
from src.config import settings
from src.trader import trader
from src import supabase_store

STATE_FILE = "executor_state.json"


def _binance_exchange_config():
    cfg = {
        'apiKey': settings.binance_api_key,
        'secret': settings.binance_secret_key,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'},
    }
    if settings.binance_proxy:
        cfg['proxies'] = {
            'http': settings.binance_proxy,
            'https': settings.binance_proxy,
        }
    if settings.binance_api_url:
        cfg['urls'] = {'api': settings.binance_api_url}
    return cfg


class Executor:
    def __init__(self):
        self._client = None
        self._sim_balance = self._tl_to_usd(settings.sim_starting_capital_tl)
        self._sim_btc = 0.0
        self._sim_entry = 0.0
        self._binance_error = None
        self._load_state()

        if settings.executor_mode == "binance" and settings.binance_api_key and settings.binance_secret_key:
            try:
                self._init_binance()
                mode = "TESTNET" if settings.binance_testnet else "LIVE"
                print(f"[EXECUTOR] Binance baglantisi basarili ({mode} modu)")
            except Exception as e:
                print(f"[EXECUTOR] UYARI: Binance baglanti hatasi: {e}")
                self._binance_error = str(e)
                settings.executor_mode = "sim"
        else:
            print("[EXECUTOR] SIM modu (Binance key yok veya mode != binance)")
            settings.executor_mode = "sim"

    def _init_binance(self):
        self._client = ccxt.binance(_binance_exchange_config())
        if settings.binance_testnet:
            self._client.set_sandbox_mode(True)
        try:
            self._client.load_markets()
        except Exception as e:
            print(f"[EXECUTOR] load_markets hatasi: {e}")

    @staticmethod
    def _binance_err(e):
        """Binance hatalarini anlasilir Turkce mesaja cevirir."""
        s = str(e)
        if "-2015" in s or "Invalid API-key" in s or "permissions for action" in s:
            return ("Binance -2015: API key gecersiz / IP izni yok / ISLEM YETKISI verilmemis. "
                    "Cozum: Binance > API Yonetimi > ilgili anahtara 'Spot & Margin Trading' "
                    "yetkisi verin; 'IP erisim kisitlamasi' aciksa sunucu IP'nizi ekleyin veya "
                    "kisitlamayi kaldirin. (Bakiye goruntuleme calisir, sadece ISLEM yapilamaz.)")
        if "API-key" in s or "permission" in s.lower():
            return "Binance API key / yetki hatasi: " + s[:200]
        if "IP" in s:
            return "Binance IP izni hatasi: " + s[:200]
        return s[:300]

    def _is_permission_error(self, e):
        s = str(e)
        return "-2015" in s or "Invalid API-key" in s or "permissions for action" in s

    def _tl_to_usd(self, tl):
        """₺ (TL) tutarini canlı USD/TRY kuruyla USD'ye çevirir."""
        rate = trader.get_usd_try_rate() or 1.0
        return float(tl) / rate if rate else float(tl)

    def _usd_to_tl(self, usd):
        """USD tutarini canlı USD/TRY kuruyla ₺'ye çevirir."""
        return float(usd) * (trader.get_usd_try_rate() or 1.0)

    def set_mode(self, mode):
        """Modu degistir: 'sim' veya 'binance'"""
        mode = mode.lower()
        if mode not in ("sim", "binance"):
            return {"success": False, "message": "Gecersiz mod"}
        if mode == "binance":
            if not settings.binance_api_key or not settings.binance_secret_key:
                return {"success": False, "message": "Binance API anahtarlari eksik! .env dosyasina BINANCE_API_KEY ve BINANCE_SECRET_KEY ekleyin."}
            try:
                self._init_binance()
                bal = self._client.fetch_balance()
                settings.executor_mode = "binance"
                return {"success": True, "message": "BINANCE moduna gecildi", "balance": bal}
            except Exception as e:
                self._binance_error = str(e)
                return {"success": False, "message": f"Binance baglanti hatasi: {str(e)[:200]}"}
        else:
            settings.executor_mode = "sim"
            return {"success": True, "message": "SIMULASYON moduna gecildi"}

    def reset_sim_balance(self, amount):
        """Simülasyon başlangıç sermayesini ayarla (sıfırlar). Tutar ₺ (TL) cinsindendir."""
        amount = float(amount)
        if amount < 0:
            return {"success": False, "message": "Sermaye 0'dan küçük olamaz"}
        usd = self._tl_to_usd(amount)
        self._sim_balance = usd
        self._sim_btc = 0.0
        self._sim_entry = 0.0
        settings.sim_starting_capital = usd
        settings.sim_starting_capital_tl = amount
        self._save_state()
        return {"success": True, "message": f"Simülasyon sermayesi ₺{amount:.2f} olarak ayarlandi", "balance": usd}

    def reset_sim(self):
        """Simülasyonu BAŞTAN sona sıfırlar. SADECE simüle edilmiş durum; Binance'e hiç dokunmaz.
        Binance modundaysa otomatik SIM'e geçer ki sıfırlama görünür olsun."""
        switched = False
        if settings.executor_mode != "sim":
            settings.executor_mode = "sim"
            switched = True
        amount = settings.sim_starting_capital_tl
        self._sim_balance = self._tl_to_usd(amount)
        self._sim_btc = 0.0
        self._sim_entry = 0.0
        settings.last_entry_price = 0
        self._save_state()
        msg = f"Simülasyon sıfırlandı (başlangıç sermaye: ₺{amount:.2f}, pozisyon kapandı)"
        if switched:
            msg += " — Binance modundan SIM'e geçildi (Binance bakiyenize dokunulmadı)"
        return {"success": True, "message": msg, "balance": amount,
                "starting_capital": amount, "switched_to_sim": switched}

    def test_binance_connection(self):
        """Binance baglantisini test et ve gercek bakiyeyi döndür."""
        if not settings.binance_api_key or not settings.binance_secret_key:
            return {"connected": False, "error": "API anahtari yok", "balance": None}
        try:
            client = ccxt.binance(_binance_exchange_config())
            if settings.binance_testnet:
                client.set_sandbox_mode(True)
            bal = client.fetch_balance()
            quote = float(bal['free'].get(settings.quote_asset, 0.0))
            base = float(bal['free'].get(settings.base_asset, 0.0))
            return {"connected": True, "error": None, "balance": {"quote": quote, "base": base}}
        except Exception as e:
            return {"connected": False, "error": str(e)[:300], "balance": None}

    def _load_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                self._sim_balance = data.get("balance", self._tl_to_usd(settings.sim_starting_capital_tl))
                self._sim_btc = data.get("btc", 0.0)
                self._sim_entry = data.get("entry", 0.0)
                print(f"[EXECUTOR] State yuklendi: bal=${self._sim_balance:.2f} btc={self._sim_btc:.6f}")
                return
        except:
            pass
        sb_data = supabase_store.load_executor_state()
        if sb_data:
            self._sim_balance = sb_data.get("balance", self._tl_to_usd(settings.sim_starting_capital_tl))
            self._sim_btc = sb_data.get("btc", 0.0)
            self._sim_entry = sb_data.get("entry", 0.0)
            print(f"[EXECUTOR] Supabase state yuklendi: bal=${self._sim_balance:.2f} btc={self._sim_btc:.6f}")
            self._save_state_local()

    def _save_state(self):
        self._save_state_local()
        supabase_store.save_executor_state(self._sim_balance, self._sim_btc, self._sim_entry)

    def _save_state_local(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({
                    "balance": self._sim_balance,
                    "btc": self._sim_btc,
                    "entry": self._sim_entry,
                }, f)
        except Exception as e:
            print(f"[EXECUTOR] State kaydetme hatasi: {e}")

    def get_account(self):
        if settings.executor_mode == "binance":
            if not self._client:
                try:
                    self._init_binance()
                except Exception as e:
                    print(f"[EXECUTOR] Binance baslatilamadi: {e}")
                    return self._dry_account()
            try:
                balance = self._client.fetch_balance()
                quote_balance = float(balance['free'].get(settings.quote_asset, 0.0))
                base_balance = float(balance['free'].get(settings.base_asset, 0.0))
                price = trader.get_price()
                portfolio_value = quote_balance + (base_balance * price)
                return {
                    "portfolio_value": round(portfolio_value, 2),
                    "cash": round(quote_balance, 2),
                    "buying_power": round(quote_balance, 2),
                    "btc": round(base_balance, 6),
                }
            except Exception as e:
                print(f"[EXECUTOR] Binance bakiye hatasi (gecici): {e}")
                return self._dry_account()
        return self._dry_account()

    def get_position(self):
        if settings.executor_mode == "binance":
            if not self._client:
                try:
                    self._init_binance()
                except:
                    return self._dry_position()
            try:
                balance = self._client.fetch_balance()
                btc_qty = float(balance['free'].get(settings.base_asset, 0.0))
                price = trader.get_price()

                if btc_qty * price > 1.0:
                    mv = round(btc_qty * price, 2)
                    entry = self._sim_entry if self._sim_entry > 0 else price
                    pl = round(mv - btc_qty * entry, 2)
                    return {
                        "symbol": settings.symbol,
                        "qty": round(btc_qty, 6),
                        "market_value": mv,
                        "avg_entry_price": entry,
                        "unrealized_pl": pl,
                    }
                return None
            except Exception as e:
                print(f"[EXECUTOR] Binance pozisyon hatasi (gecici): {e}")
                return self._dry_position()
        return self._dry_position()

    def buy(self, size_pct=100, amount_usd=None):
        if settings.executor_mode == "binance":
            if not self._client:
                try:
                    self._init_binance()
                except Exception as e:
                    print(f"[EXECUTOR] Binance baslatilamadi: {e}")
                    return self._dry_buy(size_pct, amount_usd)
            try:
                return self._binance_buy(size_pct, amount_usd)
            except Exception as e:
                if self._is_permission_error(e):
                    msg = self._binance_err(e)
                    print(f"[EXECUTOR] Binance alim YETKI HATASI: {msg}")
                    self._binance_error = msg
                    return {"error": "PERMISSION", "message": msg, "mode": "BINANCE"}
                print(f"[EXECUTOR] Binance alim hatasi (gecici): {e}")
                return self._dry_buy(size_pct, amount_usd)
        return self._dry_buy(size_pct, amount_usd)

    def sell(self):
        if settings.executor_mode == "binance":
            if not self._client:
                try:
                    self._init_binance()
                except Exception as e:
                    print(f"[EXECUTOR] Binance baslatilamadi: {e}")
                    return self._dry_sell()
            try:
                return self._binance_sell()
            except Exception as e:
                if self._is_permission_error(e):
                    msg = self._binance_err(e)
                    print(f"[EXECUTOR] Binance satis YETKI HATASI: {msg}")
                    self._binance_error = msg
                    return {"error": "PERMISSION", "message": msg, "mode": "BINANCE"}
                print(f"[EXECUTOR] Binance satis hatasi (gecici): {e}")
                return self._dry_sell()
        return self._dry_sell()

    def _dry_account(self):
        price = trader.get_price()
        btc_value = self._sim_btc * price
        portfolio = self._sim_balance + btc_value
        return {
            "portfolio_value": round(portfolio, 2),
            "cash": round(self._sim_balance, 2),
            "btc": round(self._sim_btc, 6),
            "btc_value": round(btc_value, 2),
        }

    def _dry_position(self):
        if self._sim_btc > 0.0001:
            price = trader.get_price()
            mv = round(self._sim_btc * price, 2)
            pl = round(mv - self._sim_btc * self._sim_entry, 2)
            return {
                "symbol": settings.symbol,
                "qty": round(self._sim_btc, 6),
                "market_value": mv,
                "avg_entry_price": self._sim_entry,
                "unrealized_pl": pl,
            }
        return None

    def _dry_buy(self, size_pct=100, amount_usd=None):
        price = trader.get_price()
        if price <= 0:
            return None
        invest = amount_usd if amount_usd is not None else settings.position_size_usd * (size_pct / 100)
        # Yatırım tutarını mevcut bakiyeyle sınırla (asla eksiye düşmesin).
        invest = min(invest, self._sim_balance)
        # Alınabilir miktarı yüksek hassasiyetle (8 ondalık) hesapla.
        qty = round(invest / price, 8)
        # İhmal edilebilir miktar = işlem yapılamıyor (mecburi taban KALDIRILDI,
        # aksi halde kalan küçük bakiye 0.0001 BTC (~$6) zoruyla negatife dönerdi).
        if qty <= 0 or qty * price < 0.01:
            return None
        # KOMISYON: giriş işlem ücreti (gerçek borsa gibi bakiyeden düşülür).
        fee = price * qty * settings.commission_rate
        cost = price * qty + fee
        old_btc = self._sim_btc
        # Sert güvence: bakiye asla negatif olmasın.
        self._sim_balance = max(0.0, self._sim_balance - cost)
        self._sim_btc += qty

        # Giriş maliyeti KOMİSYON DAHİL efektif fiyat olarak kaydedilir ki
        # satışta net (komisyonlu) kâr/zarar doğru hesaplansın.
        eff_entry = cost / qty
        if old_btc > 0.0001:
            self._sim_entry = round(((self._sim_entry * old_btc) + (eff_entry * qty)) / self._sim_btc, 2)
        else:
            self._sim_entry = eff_entry

        settings.last_entry_price = self._sim_entry
        self._save_state()
        return {"price": price, "qty": round(qty, 8), "cost": round(cost, 2),
                "fee": round(fee, 2), "order_id": "dry_buy", "mode": "SIM"}

    def _dry_sell(self):
        if self._sim_btc <= 0.0001:
            return None
        price = trader.get_price()
        sell_qty = self._sim_btc
        gross = price * sell_qty
        # KOMISYON: çıkış işlem ücreti (gerçek borsa gibi düşülür).
        fee = gross * settings.commission_rate
        # NET PNL: brüt gelir - çıkış komisyonu - (komisyon dahil giriş maliyeti)
        pnl = gross - fee - (self._sim_entry * sell_qty)
        cost_basis = round(sell_qty * self._sim_entry, 2)
        self._sim_balance += gross - fee
        self._sim_btc = 0.0
        self._sim_entry = 0.0
        self._save_state()
        return {"qty": round(sell_qty, 6), "pl": round(pnl, 6), "price": price,
                "gross": round(gross, 2), "fee": round(fee, 2), "cost": cost_basis,
                "order_id": "dry_sell", "mode": "SIM"}

    def _binance_buy(self, size_pct=100, amount_usd=None):
        price = trader.get_price()
        invest_amount = amount_usd if amount_usd is not None else settings.position_size_usd * (size_pct / 100)

        balance = self._client.fetch_balance()
        free_quote = float(balance['free'].get(settings.quote_asset, 0.0))
        invest_amount = min(invest_amount, free_quote * 0.99)

        if invest_amount < 10.0:
            print(f"[BINANCE] HATA: Alim tutari minimum Spot limitinin altinda: {invest_amount:.2f} {settings.quote_asset}")
            return None

        print(f"[BINANCE] Market Buy gonderiliyor: Tutar = {invest_amount:.2f} {settings.quote_asset}")

        order = None
        SYMBOL = settings.symbol
        try:
            order = self._client.create_order(
                symbol=SYMBOL,
                type='market',
                side='buy',
                amount=invest_amount,
                price=None,
                params={'quoteOrderQty': self._client.cost_to_precision(SYMBOL, invest_amount)}
            )
        except Exception as e:
            print(f"[BINANCE] quoteOrderQty hatasi, fallback yapiliyor: {e}")
            qty = invest_amount / price
            qty_prec = float(self._client.amount_to_precision(SYMBOL, qty))
            order = self._client.create_market_buy_order(SYMBOL, qty_prec)

        filled_qty = float(order.get('filled', 0.0))
        cost = float(order.get('cost', 0.0))
        avg_price = float(order.get('average', 0.0)) if order.get('average') else price

        if filled_qty == 0.0:
            try:
                time.sleep(0.5)
                order_info = self._client.fetch_order(order['id'], settings.symbol)
                filled_qty = float(order_info.get('filled', 0.0))
                cost = float(order_info.get('cost', 0.0))
                if order_info.get('average'):
                    avg_price = float(order_info['average'])
            except:
                pass

        if filled_qty == 0.0:
            filled_qty = round(invest_amount / price, 6)
            avg_price = price

        # Giriş maliyeti KOMİSYON DAHİL efektif fiyat (avg_price = zaten komisyonlu
        # ortalama fill fiyatıdır, ccxt 'cost' komisyon dahil verir).
        self._sim_entry = (cost / filled_qty) if filled_qty > 0 else avg_price
        self._sim_btc = filled_qty
        self._sim_balance = free_quote - cost if free_quote > cost else 0.0
        settings.last_entry_price = self._sim_entry
        self._save_state()

        print(f"[BINANCE] ALIS basarili: {filled_qty:.6f} {settings.base_asset} @ {avg_price:,.2f} {settings.quote_asset} (cost: {cost:.2f}, fee dahil)")
        return {"price": avg_price, "qty": round(filled_qty, 6), "order_id": str(order.get('id', 'binance_buy')), "mode": "REAL"}

    def _binance_sell(self):
        SYMBOL = settings.symbol
        balance = self._client.fetch_balance()
        btc_qty = float(balance['free'].get(settings.base_asset, 0.0))
        price = trader.get_price()

        if btc_qty * price < 10.0:
            print(f"[BINANCE] HATA: Satilacak {settings.base_asset} degeri minimum Spot limitinin altinda: {btc_qty * price:.2f} {settings.quote_asset}")
            return None

        qty_prec = float(self._client.amount_to_precision(SYMBOL, btc_qty))

        print(f"[BINANCE] Market Sell gonderiliyor: Miktar = {qty_prec:.6f} {settings.base_asset}")
        order = self._client.create_market_sell_order(SYMBOL, qty_prec)

        filled_qty = float(order.get('filled', 0.0)) if order.get('filled') else qty_prec
        cost = float(order.get('cost', 0.0))
        avg_price = float(order.get('average', 0.0)) if order.get('average') else price

        if filled_qty == 0.0:
            try:
                time.sleep(0.5)
                order_info = self._client.fetch_order(order['id'], settings.symbol)
                filled_qty = float(order_info.get('filled', 0.0))
                cost = float(order_info.get('cost', 0.0))
                if order_info.get('average'):
                    avg_price = float(order_info['average'])
            except:
                pass

        pnl = 0.0
        if self._sim_entry > 0:
            gross = avg_price * filled_qty
            fee = gross * settings.commission_rate
            pnl = gross - fee - (self._sim_entry * filled_qty)

        self._sim_entry = 0.0
        self._sim_btc = 0.0
        self._sim_balance = float(balance['free'].get(settings.quote_asset, 0.0)) + (avg_price * filled_qty) - (avg_price * filled_qty * settings.commission_rate)
        self._save_state()

        print(f"[BINANCE] SATIS basarili: {filled_qty:.6f} {settings.base_asset} @ {avg_price:,.2f} {settings.quote_asset} (NET PNL: {pnl:+.2f}, fee dahil)")
        return {"qty": round(filled_qty, 6), "pl": round(pnl, 6), "price": avg_price, "order_id": str(order.get('id', 'binance_sell')), "mode": "REAL"}


executor = Executor()
