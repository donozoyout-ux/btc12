import requests
import time


class DataFetcher:
    def __init__(self):
        self._cache = {}
        self._cache_time = {}
        self._ttl = 300

    def _get_cached(self, key, fetch_fn, ttl=None):
        ttl = ttl or self._ttl
        now = time.time()
        if key in self._cache and now - self._cache_time.get(key, 0) < ttl:
            return self._cache[key]
        try:
            data = fetch_fn()
            self._cache[key] = data
            self._cache_time[key] = now
            return data
        except:
            return self._cache.get(key)

    def fear_greed(self):
        def fetch():
            r = requests.get("https://api.alternative.me/fng/?limit=7", timeout=10)
            if r.status_code == 200:
                data = r.json().get("data", [])
                return [{
                    "value": int(d["value"]),
                    "classification": d["value_classification"],
                    "date": d.get("timestamp", "")
                } for d in data]
            return []
        return self._get_cached("fear_greed", fetch, 600)

    def fear_greed_current(self):
        fg = self.fear_greed()
        if fg:
            return fg[0]
        return {"value": 50, "classification": "Neutral"}

    def fear_greed_trend(self):
        fg = self.fear_greed()
        if len(fg) < 2:
            return 0
        return fg[0]["value"] - fg[-1]["value"]

    def coingecko_market(self):
        def fetch():
            r = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={
                    "vs_currency": "usd",
                    "ids": "bitcoin,ethereum",
                    "order": "market_cap_desc",
                    "sparkline": "false",
                    "price_change_percentage": "1h,24h,7d"
                },
                timeout=10
            )
            if r.status_code == 200:
                return r.json()
            return []
        return self._get_cached("coingecko_market", fetch, 300)

    def coingecko_trending(self):
        def fetch():
            r = requests.get("https://api.coingecko.com/api/v3/search/trending", timeout=10)
            if r.status_code == 200:
                coins = r.json().get("coins", [])
                return [{"name": c["item"]["name"], "symbol": c["item"]["symbol"],
                         "score": c["item"].get("score", 0)} for c in coins[:10]]
            return []
        return self._get_cached("coingecko_trending", fetch, 600)

    def coingecko_global(self):
        def fetch():
            r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
            if r.status_code == 200:
                return r.json().get("data", {})
            return {}
        return self._get_cached("coingecko_global", fetch, 600)

    def btc_dominance(self):
        g = self.coingecko_global()
        return g.get("market_cap_percentage", {}).get("btc", 0)

    def total_market_cap(self):
        g = self.coingecko_global()
        return g.get("total_market_cap", {}).get("usd", 0)

    def active_cryptos(self):
        g = self.coingecko_global()
        return g.get("active_cryptocurrencies", 0)


fetcher = DataFetcher()
