from src.config import settings
from src.trader import trader


class Executor:
    def __init__(self):
        self._client = None
        self._sim_balance = 1000.0
        self._sim_btc = 0.0
        self._sim_entry = 0.0
        if settings.executor_mode == "alpaca" and settings.alpaca_api_key and settings.alpaca_secret_key:
            try:
                self._init_alpaca()
                print("[EXECUTOR] Alpaca baglantisi basarili (paper=True)")
            except Exception as e:
                print(f"[EXECUTOR] Alpaca baglanti hatasi, simülasyon moduna gecildi: {e}")
                self._client = None
        else:
            print("[EXECUTOR] Simülasyon modu (Alpaca key yok veya mode != alpaca)")

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
            except:
                pass
        return self._dry_account()

    def get_position(self):
        if settings.executor_mode == "alpaca" and self._client:
            try:
                pos = self._client.get_position("BTC/USD")
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
            except:
                return None
        return self._dry_position()

    def buy(self, size_pct=100):
        if settings.executor_mode == "alpaca" and self._client:
            return self._alpaca_buy()
        return self._dry_buy(size_pct)

    def sell(self):
        if settings.executor_mode == "alpaca" and self._client:
            return self._alpaca_sell()
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
        return {"price": price, "qty": round(qty, 6), "order_id": "dry_buy"}

    def _dry_sell(self):
        if self._sim_btc <= 0.0001:
            return None
        price = trader.get_price()
        sell_qty = self._sim_btc
        pnl = (price - self._sim_entry) * sell_qty
        self._sim_balance += price * sell_qty
        self._sim_btc = 0.0
        return {"qty": round(sell_qty, 6), "pl": round(pnl, 2), "price": price, "order_id": "dry_sell"}

    def _alpaca_buy(self):
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        price = trader.get_price()
        qty = round(settings.position_size_usd / price, 6)
        qty = max(qty, 0.0001)
        try:
            order = self._client.submit_order(MarketOrderRequest(
                symbol="BTC/USD",
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC
            ))
            settings.last_entry_price = price
            return {"price": price, "qty": round(qty, 6), "order_id": str(order.id)}
        except Exception as e:
            err = str(e).lower()
            if "unauthorized" in err:
                print("[EXECUTOR] Alpaca unauthorized - API key hatali veya paper=True eksik")
            elif "minimal amount" in err or "cost basis" in err:
                print(f"[EXECUTOR] Min siparis hatasi: {e}")
            else:
                print(f"[EXECUTOR] Alpaca buy hatasi: {e}")
            raise

    def _alpaca_sell(self):
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        pos = self.get_position()
        if not pos:
            return None
        sell_qty = pos["qty"]
        order = self._client.submit_order(MarketOrderRequest(
            symbol="BTC/USD",
            qty=sell_qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        ))
        pnl = pos.get("unrealized_pl", 0)
        price = trader.get_price()
        return {"qty": round(sell_qty, 6), "pl": round(pnl, 2), "price": price, "order_id": str(order.id)}


executor = Executor()
