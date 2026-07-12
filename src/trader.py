import ccxt
import pandas as pd
from src.config import settings


class Trader:
    def __init__(self):
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
        self.exchange = ccxt.binance(cfg)
        
        if settings.binance_testnet:
            self.exchange.set_sandbox_mode(True)
            
        self.symbol = settings.symbol

    def get_price(self):
        ticker = self.exchange.fetch_ticker(self.symbol)
        return ticker['last']

    def get_bars(self, limit=100, timeframe='1m'):
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
        return df

    def get_orderbook(self, limit=50):
        book = self.exchange.fetch_order_book(self.symbol, limit=limit)
        bid_vol = sum(b[1] for b in book['bids'])
        ask_vol = sum(a[1] for a in book['asks'])

        top10_bid = sum(b[1] for b in book['bids'][:10])
        top10_ask = sum(a[1] for a in book['asks'][:10])

        imbalance = round(bid_vol / ask_vol, 2) if ask_vol > 0 else 1.0

        return {
            "bid_ask_ratio": imbalance,
            "bid_ask_sinyal": "alis_baskisi" if imbalance > 1.2 else "satis_baskisi" if imbalance < 0.8 else "notr",
            "spread": round(book['asks'][0][0] - book['bids'][0][0], 2),
            "bid_volume": round(bid_vol, 4),
            "ask_volume": round(ask_vol, 4),
            "top10_bid": round(top10_bid, 4),
            "top10_ask": round(top10_ask, 4),
        }

    def get_recent_trades(self, limit=50):
        trades = self.exchange.fetch_trades(self.symbol, limit=limit)
        buys = sum(1 for t in trades if t.get('side') == 'buy')
        return {"buy_sell_ratio": round(buys / max(len(trades) - buys, 1), 2)}

    def get_account_balance(self):
        """Gerçek Binance bakiyesini getir"""
        balance = self.exchange.fetch_balance()
        usdt = float(balance.get('USDT', {}).get('free', 0.0))
        btc = float(balance.get('BTC', {}).get('free', 0.0))
        return {"usdt": usdt, "btc": btc}

    def get_open_orders(self):
        """Açık emirleri getir"""
        return self.exchange.fetch_open_orders(self.symbol)

    def create_market_buy(self, amount_usdt):
        """Market buy order - quoteOrderQty kullanarak USDT bazında alım"""
        price = self.get_price()
        # quoteOrderQty ile USDT cinsinden alım
        order = self.exchange.create_order(
            symbol=self.symbol,
            type='market',
            side='buy',
            amount=amount_usdt,
            price=None,
            params={'quoteOrderQty': self.exchange.cost_to_precision(self.symbol, amount_usdt)}
        )
        return order

    def create_market_sell(self, amount_btc):
        """Market sell order - BTC miktarı bazında satım"""
        qty_prec = float(self.exchange.amount_to_precision(self.symbol, amount_btc))
        order = self.exchange.create_market_sell_order(self.symbol, qty_prec)
        return order


trader = Trader()
