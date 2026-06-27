from alpaca.trading.client import TradingClient
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.requests import CryptoLatestQuoteRequest
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict

from src.config import settings


class AlpacaClient:
    def __init__(self, symbol: str = None):
        self.trading_client = TradingClient(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            paper=True,
            url_override=settings.alpaca_base_url
        )
        self.data_client = CryptoHistoricalDataClient(
            settings.alpaca_api_key,
            settings.alpaca_secret_key
        )
        self.symbol_data = symbol or settings.symbols[0]  # BTC/USD
        self.symbol = self.symbol_data.replace("/", "")  # BTCUSD

    def get_account(self):
        return self.trading_client.get_account()

    def get_positions(self) -> List[Dict]:
        positions = self.trading_client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "avg_entry_price": float(p.avg_entry_price),
            }
            for p in positions
        ]

    def get_position(self, symbol: str = None) -> Dict | None:
        target = (symbol or self.symbol_data).replace("/", "")
        positions = self.get_positions()
        for p in positions:
            if p["symbol"] == target:
                return p
        return None

    def get_bars(self, symbol: str = None, limit: int = 100) -> pd.DataFrame:
        from datetime import timezone
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=6)
        target = symbol or self.symbol_data

        request = CryptoBarsRequest(
            symbol_or_symbols=[target],
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            limit=limit
        )
        bars = self.data_client.get_crypto_bars(request)
        df = bars.df
        if df.empty:
            return pd.DataFrame()

        if isinstance(df.index, pd.MultiIndex):
            df = df.droplevel(0)

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"timestamp": "datetime"})
        return df[["datetime", "open", "high", "low", "close", "volume"]]

    def get_latest_price(self, symbol: str = None) -> float:
        target = symbol or self.symbol_data
        request = CryptoLatestQuoteRequest(symbol_or_symbols=target)
        quote = self.data_client.get_crypto_latest_quote(request)
        return float(quote[target].ask_price)

    def place_market_order(self, side: OrderSide, qty: float, symbol: str = None) -> Dict:
        target = (symbol or self.symbol_data).replace("/", "")
        order = MarketOrderRequest(
            symbol=target,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC
        )
        result = self.trading_client.submit_order(order)
        return {
            "id": result.id,
            "symbol": result.symbol,
            "qty": float(result.qty),
            "side": result.side.value,
            "status": result.status.value,
            "filled_avg_price": float(result.filled_avg_price) if result.filled_avg_price else None
        }

    def place_limit_order(self, side: OrderSide, qty: float, limit_price: float, symbol: str = None) -> Dict:
        target = (symbol or self.symbol_data).replace("/", "")
        order = LimitOrderRequest(
            symbol=target,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.GTC,
            limit_price=limit_price
        )
        result = self.trading_client.submit_order(order)
        return {
            "id": result.id,
            "symbol": result.symbol,
            "qty": float(result.qty),
            "side": result.side.value,
            "status": result.status.value,
            "limit_price": limit_price
        }

    def place_stop_loss(self, qty: float, stop_price: float, symbol: str = None) -> Dict:
        target = (symbol or self.symbol_data).replace("/", "")
        order = StopOrderRequest(
            symbol=target,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            stop_price=stop_price
        )
        result = self.trading_client.submit_order(order)
        return {
            "id": result.id,
            "symbol": result.symbol,
            "qty": float(result.qty),
            "side": result.side.value,
            "status": result.status.value,
            "stop_price": stop_price
        }

    def get_orders(self, status: str = "open") -> List[Dict]:
        orders = self.trading_client.get_orders(status=status)
        return [
            {
                "id": o.id,
                "symbol": o.symbol,
                "qty": float(o.qty),
                "side": o.side.value,
                "status": o.status.value,
                "type": o.order_type.value,
                "limit_price": float(o.limit_price) if o.limit_price else None,
                "stop_price": float(o.stop_price) if o.stop_price else None,
            }
            for o in orders
        ]

    def cancel_order(self, order_id: str):
        self.trading_client.cancel_order_by_id(order_id)

    def cancel_all_orders(self):
        self.trading_client.cancel_orders()

    def calculate_qty(self, usd_amount: float, price: float) -> float:
        return round(usd_amount / price, 6)

    def get_clock(self):
        return self.trading_client.get_clock()