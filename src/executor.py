import json
import os
import time
import ccxt
from src.config import settings
from src.trader import trader
from src import supabase_store

SYMBOL = "BTC/USDT"
STATE_FILE = "executor_state.json"


class Executor:
    def __init__(self):
        self._client = None
        self._sim_balance = 100000.0
        self._sim_btc = 0.0
        self._sim_entry = 0.0
        self._bybit_error = None
        self._load_state()

        if settings.executor_mode == "bybit" and settings.bybit_api_key and settings.bybit_secret_key:
            try:
                self._init_bybit()
                print(f"[EXECUTOR] Bybit baglantisi basarili (testnet={settings.bybit_testnet})")
            except Exception as e:
                print(f"[EXECUTOR] UYARI: Bybit baglanti hatasi (gecici olabilir): {e}")
                self._bybit_error = str(e)
        else:
            print("[EXECUTOR] SIM modu (Bybit key yok veya mode != bybit)")
            settings.executor_mode = "sim"

    def _init_bybit(self):
        self._client = ccxt.bybit({
            'apiKey': settings.bybit_api_key,
            'secret': settings.bybit_secret_key,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'},
        })
        if settings.bybit_testnet:
            self._client.set_sandbox_mode(True)
        try:
            self._client.load_markets()
        except Exception as e:
            print(f"[EXECUTOR] load_markets hatasi: {e}")

    def _load_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                self._sim_balance = data.get("balance", 100000.0)
                self._sim_btc = data.get("btc", 0.0)
                self._sim_entry = data.get("entry", 0.0)
                print(f"[EXECUTOR] State yuklendi: bal=${self._sim_balance:.2f} btc={self._sim_btc:.6f}")
                return
        except:
            pass
        sb_data = supabase_store.load_executor_state()
        if sb_data:
            self._sim_balance = sb_data.get("balance", 100000.0)
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
        if settings.executor_mode == "bybit":
            if not self._client:
                try:
                    self._init_bybit()
                except Exception as e:
                    print(f"[EXECUTOR] Bybit baslatilamadi: {e}")
                    return self._dry_account()
            try:
                balance = self._client.fetch_balance()
                usdt_balance = float(balance['free'].get('USDT', 0.0))
                btc_balance = float(balance['free'].get('BTC', 0.0))
                price = trader.get_price()
                portfolio_value = usdt_balance + (btc_balance * price)
                return {
                    "portfolio_value": round(portfolio_value, 2),
                    "cash": round(usdt_balance, 2),
                    "buying_power": round(usdt_balance, 2),
                    "btc": round(btc_balance, 6),
                }
            except Exception as e:
                print(f"[EXECUTOR] Bybit bakiye hatasi (gecici): {e}")
                return self._dry_account()
        return self._dry_account()

    def get_position(self):
        if settings.executor_mode == "bybit":
            if not self._client:
                try:
                    self._init_bybit()
                except:
                    return self._dry_position()
            try:
                balance = self._client.fetch_balance()
                btc_qty = float(balance['free'].get('BTC', 0.0))
                price = trader.get_price()

                if btc_qty * price > 1.0:
                    mv = round(btc_qty * price, 2)
                    entry = self._sim_entry if self._sim_entry > 0 else price
                    pl = round(mv - btc_qty * entry, 2)
                    return {
                        "symbol": SYMBOL,
                        "qty": round(btc_qty, 6),
                        "market_value": mv,
                        "avg_entry_price": entry,
                        "unrealized_pl": pl,
                    }
                return None
            except Exception as e:
                print(f"[EXECUTOR] Bybit pozisyon hatasi (gecici): {e}")
                return self._dry_position()
        return self._dry_position()

    def buy(self, size_pct=100, amount_usd=None):
        if settings.executor_mode == "bybit":
            if not self._client:
                try:
                    self._init_bybit()
                except Exception as e:
                    print(f"[EXECUTOR] Bybit baslatilamadi: {e}")
                    return self._dry_buy(size_pct, amount_usd)
            try:
                return self._bybit_buy(size_pct, amount_usd)
            except Exception as e:
                print(f"[EXECUTOR] Bybit alim hatasi (gecici): {e}")
                return self._dry_buy(size_pct, amount_usd)
        return self._dry_buy(size_pct, amount_usd)

    def sell(self):
        if settings.executor_mode == "bybit":
            if not self._client:
                try:
                    self._init_bybit()
                except Exception as e:
                    print(f"[EXECUTOR] Bybit baslatilamadi: {e}")
                    return self._dry_sell()
            try:
                return self._bybit_sell()
            except Exception as e:
                print(f"[EXECUTOR] Bybit satis hatasi (gecici): {e}")
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
                "symbol": SYMBOL,
                "qty": round(self._sim_btc, 6),
                "market_value": mv,
                "avg_entry_price": self._sim_entry,
                "unrealized_pl": pl,
            }
        return None

    def _dry_buy(self, size_pct=100, amount_usd=None):
        price = trader.get_price()
        invest = amount_usd if amount_usd is not None else settings.position_size_usd * (size_pct / 100)
        qty = round(invest / price, 6)
        qty = max(qty, 0.0001)
        cost = price * qty
        if cost > self._sim_balance:
            qty = round(self._sim_balance / price, 6)
            qty = max(qty, 0.0001)
            cost = price * qty
        self._sim_balance -= cost
        self._sim_btc += qty
        self._sim_entry = price
        settings.last_entry_price = price
        self._save_state()
        return {"price": price, "qty": round(qty, 6), "order_id": "dry_buy", "mode": "SIM"}

    def _dry_sell(self):
        if self._sim_btc <= 0.0001:
            return None
        price = trader.get_price()
        sell_qty = self._sim_btc
        pnl = (price - self._sim_entry) * sell_qty
        self._sim_balance += price * sell_qty
        self._sim_btc = 0.0
        self._sim_entry = 0.0
        self._save_state()
        return {"qty": round(sell_qty, 6), "pl": round(pnl, 2), "price": price, "order_id": "dry_sell", "mode": "SIM"}

    def _bybit_buy(self, size_pct=100, amount_usd=None):
        price = trader.get_price()
        invest_amount = amount_usd if amount_usd is not None else settings.position_size_usd * (size_pct / 100)

        balance = self._client.fetch_balance()
        free_usdt = float(balance['free'].get('USDT', 0.0))
        invest_amount = min(invest_amount, free_usdt * 0.99)

        if invest_amount < 1.0:
            print(f"[BYBIT] HATA: Alim tutari cok dusuk: ${invest_amount:.2f}")
            return None

        print(f"[BYBIT] Market Buy gonderiliyor: Tutar = {invest_amount:.2f} USDT")

        # Bybit spot market buy - miktar BTC cinsinden
        qty = invest_amount / price
        qty_prec = float(self._client.amount_to_precision(SYMBOL, qty))
        order = self._client.create_market_buy_order(SYMBOL, qty_prec)

        filled_qty = float(order.get('filled', 0.0))
        cost = float(order.get('cost', 0.0))
        avg_price = float(order.get('average', 0.0)) if order.get('average') else price

        if filled_qty == 0.0:
            try:
                time.sleep(1)
                order_info = self._client.fetch_order(order['id'], SYMBOL)
                filled_qty = float(order_info.get('filled', 0.0))
                cost = float(order_info.get('cost', 0.0))
                if order_info.get('average'):
                    avg_price = float(order_info['average'])
            except:
                pass

        if filled_qty == 0.0:
            filled_qty = qty_prec
            avg_price = price
            cost = invest_amount

        self._sim_entry = avg_price
        self._sim_btc = filled_qty
        self._sim_balance = free_usdt - cost if free_usdt > cost else 0.0
        settings.last_entry_price = avg_price
        self._save_state()

        print(f"[BYBIT] ALIS basarili: {filled_qty:.6f} BTC @ ${avg_price:,.2f} (cost: ${cost:.2f})")
        return {"price": avg_price, "qty": round(filled_qty, 6), "order_id": str(order.get('id', 'bybit_buy')), "mode": "REAL"}

    def _bybit_sell(self):
        balance = self._client.fetch_balance()
        btc_qty = float(balance['free'].get('BTC', 0.0))
        price = trader.get_price()

        if btc_qty * price < 1.0:
            print(f"[BYBIT] HATA: Satilacak BTC degeri cok dusuk: ${btc_qty * price:.2f}")
            return None

        qty_prec = float(self._client.amount_to_precision(SYMBOL, btc_qty))

        print(f"[BYBIT] Market Sell gonderiliyor: Miktar = {qty_prec:.6f} BTC")
        order = self._client.create_market_sell_order(SYMBOL, qty_prec)

        filled_qty = float(order.get('filled', 0.0)) if order.get('filled') else qty_prec
        cost = float(order.get('cost', 0.0))
        avg_price = float(order.get('average', 0.0)) if order.get('average') else price

        if filled_qty == 0.0:
            try:
                time.sleep(1)
                order_info = self._client.fetch_order(order['id'], SYMBOL)
                filled_qty = float(order_info.get('filled', 0.0))
                cost = float(order_info.get('cost', 0.0))
                if order_info.get('average'):
                    avg_price = float(order_info['average'])
            except:
                pass

        pnl = 0.0
        if self._sim_entry > 0:
            pnl = (avg_price - self._sim_entry) * filled_qty

        self._sim_entry = 0.0
        self._sim_btc = 0.0
        self._sim_balance = float(balance['free'].get('USDT', 0.0)) + cost
        self._save_state()

        print(f"[BYBIT] SATIS basarili: {filled_qty:.6f} BTC @ ${avg_price:,.2f} (PNL: ${pnl:+.2f})")
        return {"qty": round(filled_qty, 6), "pl": round(pnl, 2), "price": avg_price, "order_id": str(order.get('id', 'bybit_sell')), "mode": "REAL"}


executor = Executor()
