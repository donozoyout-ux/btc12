from src.config import settings
from src.trader import trader


class Executor:
    def __init__(self):
        self.mode = settings.executor_mode
        self._api = None
        self._sim_balance = 1000.0
        self._sim_btc = 0.0
        self._sim_entry = 0.0
        if self.mode == "alpaca":
            self._init_alpaca()

    def _init_alpaca(self):
        from alpaca.trading.client import TradingClient
        self._client = TradingClient(
            settings.alpaca_api_key,
            settings.alpaca_secret_key
        )

    def get_account(self):
        if self.mode == "alpaca":
            return self._alpaca_account()
        return self._dry_account()

    def get_position(self):
        if self.mode == "alpaca":
            return self._alpaca_position()
        return self._dry_position()

    def buy(self, qty=None):
        if self.mode == "alpaca":
            return self._alpaca_buy(qty)
        return self._dry_buy(qty)

    def sell(self, qty=None):
        if self.mode == "alpaca":
            return self._alpaca_sell(qty)
        return self._dry_sell(qty)

    def sell_all(self):
        if self.mode == "alpaca":
            return self._alpaca_sell_all()
        return self._dry_sell_all()

    def _dry_account(self):
        price = trader.get_price()
        btc_value = self._sim_btc * price
        portfolio = self._sim_balance + btc_value
        return {
            "portfolio_value": round(portfolio, 2),
            "cash": round(self._sim_balance, 2),
            "buying_power": round(self._sim_balance, 2),
            "btc": round(self._sim_btc, 6),
            "btc_value": round(btc_value, 2),
        }

    def _dry_position(self):
        if self._sim_btc > 0.0001:
            price = trader.get_price()
            mv = round(self._sim_btc * price, 2)
            pl = round(mv - self._sim_btc * self._sim_entry, 2) if self._sim_entry > 0 else 0
            return {
                "symbol": "BTC/USDT",
                "qty": round(self._sim_btc, 6),
                "market_value": mv,
                "avg_entry_price": self._sim_entry,
                "unrealized_pl": pl,
            }
        return None

    def _dry_buy(self, qty=None):
        price = trader.get_price()
        qty = qty or round(settings.position_size_usd / price, 6)
        qty = max(qty, 0.0001)
        cost = price * qty
        if cost > self._sim_balance:
            raise Exception(f"Yetersiz bakiye: ${self._sim_balance:.2f} < ${cost:.2f}")
        self._sim_balance -= cost
        self._sim_btc += qty
        self._sim_entry = price
        settings.last_entry_price = price
        print(f"[DRY-RUN] BUY {qty:.6f} BTC @ ${price:,.2f} | Kalan: ${self._sim_balance:.2f}")
        return {"price": price, "qty": round(qty, 6), "order_id": "dry_run"}

    def _dry_sell(self, qty=None):
        if self._sim_btc <= 0.0001:
            return None
        price = trader.get_price()
        sell_qty = qty or self._sim_btc
        pnl = (price - self._sim_entry) * sell_qty
        self._sim_balance += price * sell_qty
        self._sim_btc -= sell_qty
        print(f"[DRY-RUN] SELL {sell_qty:.6f} BTC @ ${price:,.2f} | K/Z: ${pnl:+,.2f}")
        return {"qty": round(sell_qty, 6), "pl": round(pnl, 2), "order_id": "dry_run"}

    def _dry_sell_all(self):
        if self._sim_btc <= 0.0001:
            return []
        result = self._dry_sell()
        return [result] if result else []

    def _alpaca_account(self):
        acc = self._client.get_account()
        return {
            "portfolio_value": round(float(acc.portfolio_value), 2),
            "cash": round(float(acc.cash), 2),
            "buying_power": round(float(acc.buying_power), 2),
            "btc": 0,
            "btc_value": 0,
        }

    def _alpaca_position(self):
        try:
            pos = self._client.get_position("BTC/USD")
            entry = float(pos.avg_entry_price)
            qty = float(pos.qty)
            price = trader.get_price()
            mv = round(qty * price, 2)
            pl = round(mv - qty * entry, 2) if entry > 0 else 0
            return {
                "symbol": "BTC/USD",
                "qty": round(qty, 6),
                "market_value": mv,
                "avg_entry_price": entry,
                "unrealized_pl": pl,
            }
        except Exception:
            return None

    def _alpaca_buy(self, qty=None):
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        price = trader.get_price()
        qty = qty or round(settings.position_size_usd / price, 6)
        qty = max(qty, 0.0001)
        order = self._client.submit_order(MarketOrderRequest(
            symbol='BTC/USD',
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC
        ))
        settings.last_entry_price = price
        return {"price": price, "qty": round(qty, 6), "order_id": str(order.id)}

    def _alpaca_sell(self, qty=None):
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        pos = self._alpaca_position()
        if not pos:
            return None
        sell_qty = qty or pos["qty"]
        order = self._client.submit_order(MarketOrderRequest(
            symbol='BTC/USD',
            qty=sell_qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC
        ))
        pnl = pos.get("unrealized_pl", 0)
        return {"qty": round(sell_qty, 6), "pl": round(pnl, 2), "order_id": str(order.id)}

    def _alpaca_sell_all(self):
        try:
            self._client.close_position("BTC/USD")
            return [{"qty": 0, "pl": 0, "order_id": "closed"}]
        except Exception:
            return []


executor = Executor()
