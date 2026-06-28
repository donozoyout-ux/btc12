from alpaca.trading.client import TradingClient
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, CryptoLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from datetime import datetime, timedelta, timezone
import pandas as pd
from src.config import settings


class Trader:
    def __init__(self):
        self.trading = TradingClient(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            paper=True,
            url_override=settings.alpaca_base_url
        )
        self.data = CryptoHistoricalDataClient(
            settings.alpaca_api_key,
            settings.alpaca_secret_key
        )

    def get_account(self):
        acc = self.trading.get_account()
        return {
            "portfolio_value": float(acc.portfolio_value),
            "cash": float(acc.cash),
            "buying_power": float(acc.buying_power),
        }

    def get_positions(self):
        positions = self.trading.get_all_positions()
        return [{
            "symbol": p.symbol,
            "qty": float(p.qty),
            "market_value": float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
            "avg_entry_price": float(p.avg_entry_price),
        } for p in positions]

    def get_position(self, symbol):
        target = symbol.replace("/", "")
        for p in self.get_positions():
            if p["symbol"] == target:
                return p
        return None

    def get_price(self, symbol):
        req = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
        quote = self.data.get_crypto_latest_quote(req)
        return float(quote[symbol].ask_price)

    def get_bars(self, symbol, limit=60):
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=6)
        req = CryptoBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Minute,
            start=start, end=end, limit=limit
        )
        bars = self.data.get_crypto_bars(req)
        df = bars.df
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.index, pd.MultiIndex):
            df = df.droplevel(0)
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"timestamp": "datetime"})
        return df[["datetime", "open", "high", "low", "close", "volume"]]

    def buy(self, symbol, qty=None):
        price = self.get_price(symbol)
        if qty is None:
            qty = round(settings.position_size_usd / price, 6)
        self.trading.submit_order(MarketOrderRequest(
            symbol=symbol.replace("/", ""), qty=qty,
            side=OrderSide.BUY, time_in_force=TimeInForce.GTC
        ))
        sl = round(price * (1 - settings.stop_loss_pct), 2)
        tp = round(price * (1 + settings.take_profit_pct), 2)
        self.trading.submit_order(StopOrderRequest(
            symbol=symbol.replace("/", ""), qty=qty,
            side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
            stop_price=sl
        ))
        self.trading.submit_order(LimitOrderRequest(
            symbol=symbol.replace("/", ""), qty=qty,
            side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
            limit_price=tp
        ))
        return {"price": price, "qty": qty, "sl": sl, "tp": tp}

    def sell(self, symbol, qty=None):
        pos = self.get_position(symbol)
        if not pos:
            return None
        self.trading.cancel_orders()
        sell_qty = qty if qty else pos["qty"]
        self.trading.submit_order(MarketOrderRequest(
            symbol=symbol.replace("/", ""), qty=sell_qty,
            side=OrderSide.SELL, time_in_force=TimeInForce.GTC
        ))
        return {"qty": sell_qty, "pl": pos.get("unrealized_pl", 0)}

    def sell_all(self):
        results = []
        for p in self.get_positions():
            try:
                self.trading.cancel_orders()
                self.trading.submit_order(MarketOrderRequest(
                    symbol=p["symbol"], qty=p["qty"],
                    side=OrderSide.SELL, time_in_force=TimeInForce.GTC
                ))
                results.append({"symbol": p["symbol"], "pl": p.get("unrealized_pl", 0)})
            except:
                pass
        return results

    def cancel_orders(self):
        self.trading.cancel_orders()


trader = Trader()
