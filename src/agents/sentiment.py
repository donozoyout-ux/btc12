class SentimentAgent:
    name = "SENTIMENT"
    icon = "mood"

    def analyze(self, df, symbol=None):
        from src.agents.data import fetcher

        fg = fetcher.fear_greed_current()
        fg_trend = fetcher.fear_greed_trend()
        fg_value = fg.get("value", 50)
        fg_class = fg.get("classification", "Neutral")

        trending = fetcher.coingecko_trending()
        btc_dom = fetcher.btc_dominance()

        buy = 0
        sell = 0
        reasons = []

        if fg_value < 20:
            buy += 0.35
            reasons.append(f"Buyuk korku ({fg_value} - {fg_class})")
        elif fg_value < 30:
            buy += 0.2
            reasons.append(f"Korku ({fg_value} - {fg_class})")
        elif fg_value < 40:
            buy += 0.1
        elif fg_value > 80:
            sell += 0.35
            reasons.append(f"Buyuk acg ozluluk ({fg_value} - {fg_class})")
        elif fg_value > 70:
            sell += 0.2
            reasons.append(f"Acg ozluluk ({fg_value} - {fg_class})")
        elif fg_value > 60:
            sell += 0.1

        if fg_trend < -15:
            buy += 0.15
            reasons.append(f"Korku artiyor ({fg_trend:+d})")
        elif fg_trend > 15:
            sell += 0.15
            reasons.append(f"Acg ozluluk artiyor ({fg_trend:+d})")

        market = fetcher.coingecko_market()
        for coin in market:
            pct_24h = coin.get("price_change_percentage_24h", 0) or 0
            if coin.get("symbol", "").upper() == "BTC":
                if pct_24h < -5:
                    buy += 0.1
                    reasons.append(f"BTC 24s dusus ({pct_24h:+.1f}%)")
                elif pct_24h > 5:
                    sell += 0.1
                    reasons.append(f"BTC 24s yukselis ({pct_24h:+.1f}%)")

        btc_trending = any("bitcoin" in t.get("name", "").lower() or "btc" in t.get("symbol", "").lower() for t in trending)
        eth_trending = any("ethereum" in t.get("name", "").lower() or "eth" in t.get("symbol", "").lower() for t in trending)

        if btc_trending:
            reasons.append("BTC trending'de")
        if eth_trending:
            reasons.append("ETH trending'de")

        if btc_dom > 55:
            sell += 0.05
            reasons.append(f"BTC dominance yuksek (%{btc_dom:.1f})")
        elif btc_dom < 40:
            buy += 0.05
            reasons.append(f"BTC dominance dusuk (%{btc_dom:.1f})")

        buy = min(buy, 1.0)
        sell = min(sell, 1.0)

        if buy > sell and buy > 0.2:
            return {"direction": "BUY", "confidence": buy, "reason": "; ".join(reasons),
                    "fear_greed": fg_value, "fg_class": fg_class, "btc_dominance": btc_dom}
        elif sell > buy and sell > 0.2:
            return {"direction": "SELL", "confidence": sell, "reason": "; ".join(reasons),
                    "fear_greed": fg_value, "fg_class": fg_class, "btc_dominance": btc_dom}
        return {"direction": "NEUTRAL", "confidence": max(buy, sell), "reason": "Piyasa nötr",
                "fear_greed": fg_value, "fg_class": fg_class, "btc_dominance": btc_dom}
