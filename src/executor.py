import json
import os
from src.config import settings
from src.trader import trader
from src import supabase_store

ALPACA_SYMBOL = "BTCUSD"
STATE_FILE = "executor_state.json"


class Executor:
    def __init__(self):
        self._client = None
        self._sim_balance = 100000.0
        self._sim_btc = 0.0
        self._sim_entry = 0.0
        self._alpaca_error = None
        self._load_state()
        if settings.executor_mode == "alpaca" and settings.alpaca_api_key and settings.alpaca_secret_key:
            try:
                self._init_alpaca()
                self._test_connection()
                print("[EXECUTOR] Alpaca baglantisi basarili (paper=True)")
            except Exception as e:
                print(f"[EXECUTOR] Alpaca baglanti hatasi: {e}")
                print("[EXECUTOR] SIM moda geciliyor...")
                self._client = None
                settings.executor_mode = "sim"
        else:
            print("[EXECUTOR] SIM modu (Alpaca key yok veya mode != alpaca)")
            settings.executor_mode = "sim"

    def _test_connection(self):
        try:
            self._client.get_account()
        except Exception as e:
            raise Exception(f"Alpaca test failed: {e}")

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

    def _init_alpaca(self):
        from alpaca.trading.client import TradingClient
        self._client = TradingClient(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            paper=True
        )

    def get_account(self):
        if settings.executor_mode == "alpaca" and self._client:
            try:
                acc = self._client.get_account()
                return {
                    "portfolio_value": round(float(acc.portfolio_value), 2),
                    "cash": round(float(acc.cash), 2),
                    "buying_power": round(float(acc.buying_power), 2),
                }
            except Exception as e:
                print(f"[EXECUTOR] Alpaca account hatasi: {e}, SIM'e donuluyor")
                settings.executor_mode = "sim"
                self._client = None
        return self._dry_account()

    def get_position(self):
        if settings.executor_mode == "alpaca" and self._client:
            try:
                for pos in self._client.get_all_positions():
                    if pos.symbol.upper() in ("BTCUSD", "BTC/USD"):
                        price = trader.get_price()
                        entry = float(pos.avg_entry_price)
                        qty = float(pos.qty)
                        mv = round(qty * price, 2)
                        pl = round(mv - qty * entry, 2)
                        return {
                            "symbol": "BTC/USD",
                            "qty": round(qty, 6),
                            "market_value": mv,
                            "avg_entry_price": entry,
                            "unrealized_pl": pl,
                        }
                return None
            except Exception as e:
                print(f"[EXECUTOR] Alpaca pozisyon hatasi: {e}")
                return None
        return self._dry_position()

    def buy(self, size_pct=100):
        if settings.executor_mode == "alpaca" and self._client:
            try:
                return self._alpaca_buy(size_pct)
            except Exception as e:
                print(f"[EXECUTOR] Alpaca alim hatasi: {e}, SIM'e donuluyor")
                settings.executor_mode = "sim"
                self._client = None
        return self._dry_buy(size_pct)

    def sell(self):
        if settings.executor_mode == "alpaca" and self._client:
            try:
                return self._alpaca_sell()
            except Exception as e:
                print(f"[EXECUTOR] Alpaca satis hatasi: {e}, SIM'e donuluyor")
                settings.executor_mode = "sim"
                self._client = None
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
                "symbol": "BTC/USDT",
                "qty": round(self._sim_btc, 6),
                "market_value": mv,
                "avg_entry_price": self._sim_entry,
                "unrealized_pl": pl,
            }
        return None

    def _dry_buy(self, size_pct=100):
        price = trader.get_price()
        invest = settings.position_size_usd * (size_pct / 100)
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

    def _alpaca_buy(self, size_pct=100):
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        price = trader.get_price()
        try:
            acc = self._client.get_account()
            cash = float(acc.cash)
        except:
            cash = settings.position_size_usd
        invest_amount = min(cash * 0.95, cash)
        qty = round(invest_amount / price, 6)
        qty = max(qty, 0.0001)
        order = self._client.submit_order(MarketOrderRequest(
            symbol=ALPACA_SYMBOL,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC
        ))
        settings.last_entry_price = price
        return {"price": price, "qty": round(qty, 6), "order_id": str(order.id), "mode": "REAL"}

    def _alpaca_sell(self):
        pos = self.get_position()
        if not pos:
            return None
        sell_qty = pos["qty"]
        self._client.close_position(ALPACA_SYMBOL)
        pnl = pos.get("unrealized_pl", 0)
        price = trader.get_price()
        return {"qty": round(sell_qty, 6), "pl": round(pnl, 2), "price": price, "order_id": "close_position", "mode": "REAL"}


executor = Executor()
