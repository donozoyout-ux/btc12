import requests
import time


class CoinGeckoAPI:
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.cache = {}
        self.cache_time = 0
        self.cache_ttl = 300

    def get_top_coins(self, limit: int = 100) -> list:
        now = time.time()
        if "coins" in self.cache and now - self.cache_time < self.cache_ttl:
            return self.cache["coins"]

        try:
            url = f"{self.base_url}/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "1h,24h,7d"
            }
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                self.cache["coins"] = data
                self.cache_time = now
                return data
        except Exception as e:
            print(f"CoinGecko error: {e}")

        return self.cache.get("coins", [])

    def get_trending(self) -> list:
        try:
            url = f"{self.base_url}/search/trending"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("coins", [])
        except:
            pass
        return []

    def get_fear_greed(self) -> dict:
        try:
            url = "https://api.alternative.me/fng/"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data"):
                    return data["data"][0]
        except:
            pass
        return {"value": "50", "value_classification": "Neutral"}

    def get_global(self) -> dict:
        try:
            url = f"{self.base_url}/global"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", {})
        except:
            pass
        return {}

    def map_to_alpaca_symbol(self, coin_id: str) -> str:
        mapping = {
            "bitcoin": "BTC/USD",
            "ethereum": "ETH/USD",
            "solana": "SOL/USD",
            "ripple": "XRP/USD",
            "dogecoin": "DOGE/USD",
            "cardano": "ADA/USD",
            "avalanche-2": "AVAX/USD",
            "chainlink": "LINK/USD",
            "polkadot": "DOT/USD",
            "sui": "SUI/USD",
            "pepe": "PEPE/USD",
            "shiba-inu": "SHIB/USD",
            "bonk": "BONK/USD",
            "dogwifcoin": "WIF/USD",
            "official-trump": "TRUMP/USD",
            "arbitrum": "ARB/USD",
            "optimism": "OP/USD",
            "aptos": "APT/USD",
            "matic-network": "POL/USD",
            "filecoin": "FIL/USD",
            "uniswap": "UNI/USD",
            "aave": "AAVE/USD",
            "litecoin": "LTC/USD",
            "bitcoin-cash": "BCH/USD",
            "curve-dao-token": "CRV/USD",
            "lido-dao": "LDO/USD",
            "the-graph": "GRT/USD",
            "render-token": "RENDER/USD",
            "sushi": "SUSHI/USD",
            "basic-attention-token": "BAT/USD",
            "ondo-finance": "ONDO/USD",
            "pax-gold": "PAXG/USD",
            "hyperliquid": "HYPE/USD",
            "cosmos": "ATOM/USD",
            "near": "NEAR/USD",
            "sei-network": "SEI/USD",
            "injective-protocol": "INJ/USD",
            "jupiter-exchange-solana": "JUP/USD",
            "worldcoin-wld": "WLD/USD",
            "fantom": "FTM/USD",
            "the-sandbox": "SAND/USD",
            "decentraland": "MANA/USD",
            "axie-infinity": "AXS/USD",
            "gala": "GALA/USD",
            "notcoin": "NOT/USD",
            "turbo": "TURBO/USD",
            "tron": "TRX/USD",
            "internet-computer": "ICP/USD",
            "celestia": "TIA/USD",
            "pyth-network": "PYTH/USD",
            "stax": "SKY/USD",
            "algorand": "ALGO/USD",
            "vechain": "VET/USD",
            "hedera-hashgraph": "HBAR/USD",
            "mantle": "MNT/USD",
            "kaspa": "KAS/USD",
            "sei": "SEI/USD",
            "bonk": "BONK/USD",
            "floki": "FLOKI/USD",
            "PENDLE": "PENDLE/USD",
            "jupiter": "JUP/USD",
            "wormhole": "W/USD",
            "celestia": "TIA/USD",
            "jito-governance-token": "JTO/USD",
            "dydx-chain": "DYDX/USD",
            "tokenize-xchange": "TKX/USD",
            "gate-token": "GT/USD",
            "kucoin-shares": "KCS/USD",
            "leo-token": "LEO/USD",
            "crypto-com-chain": "CRO/USD",
            "huobi-token": "HT/USD",
            "bittensor": "TAO/USD",
            "arweave": "AR/USD",
            "floki-inu": "FLOKI/USD",
            "wormhole": "W/USD",
            "jito": "JTO/USD",
            "bonk": "BONK/USD",
        }

        if coin_id in mapping:
            return mapping[coin_id]

        return None


coingecko = CoinGeckoAPI()
