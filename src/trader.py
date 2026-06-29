import ccxt
import pandas as pd
from src.config import settings


class Trader:
    def __init__(self):
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'},
        })
        self.symbol = "BTC/USDT"

    def get_price(self):
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker['last']

    def get_bars(self, limit=100, timeframe='1m'):
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
        return df

    def get_orderbook(self, limit=10):
        book = self.exchange.fetch_order_book(self.symbol, limit=limit)
        bid_vol = sum(b[1] for b in book['bids'])
        ask_vol = sum(a[1] for a in book['asks'])
        return {
            "bid_ask_ratio": round(bid_vol / ask_vol, 2) if ask_vol > 0 else 1,
            "spread": round(book['asks'][0][0] - book['bids'][0][0], 2),
            "bid_volume": bid_vol,
            "ask_volume": ask_vol
        }

    def get_recent_trades(self, limit=50):
        trades = self.exchange.fetch_trades(self.symbol, limit=limit)
        buys = sum(1 for t in trades if t.get('side') == 'buy')
        return {"buy_sell_ratio": round(buys / max(len(trades) - buys, 1), 2)}


trader = Trader()
