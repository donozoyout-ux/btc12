import requests
import time
from xml.etree import ElementTree


class NewsFetcher:
    def __init__(self):
        self._cache = []
        self._cache_time = 0
        self._ttl = 300

    def fetch_bitcoin_news(self, limit=5):
        now = time.time()
        if self._cache and now - self._cache_time < self._ttl:
            return self._cache

        try:
            r = requests.get(
                "https://cointelegraph.com/rss/tag/bitcoin",
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code != 200:
                return self._cache or []

            root = ElementTree.fromstring(r.content)
            items = []
            for item in root.iter("{http://www.w3.org/2005/Atom}entry"):
                title = item.find("{http://www.w3.org/2005/Atom}title")
                if title is not None and title.text:
                    items.append({
                        "baslik": title.text.strip(),
                        "sentiment": self._analyze_sentiment(title.text)
                    })
                if len(items) >= limit:
                    break

            if not items:
                for item in root.iter("item"):
                    title = item.find("title")
                    if title is not None and title.text:
                        items.append({
                            "baslik": title.text.strip(),
                            "sentiment": self._analyze_sentiment(title.text)
                        })
                    if len(items) >= limit:
                        break

            self._cache = items
            self._cache_time = now
            return items

        except Exception:
            return self._cache or []

    def _analyze_sentiment(self, text):
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            analyzer = SentimentIntensityAnalyzer()
            scores = analyzer.polarity_scores(text)
            if scores["compound"] >= 0.2:
                return "pozitif"
            elif scores["compound"] <= -0.2:
                return "negatif"
            return "notr"
        except ImportError:
            return "notr"


news_fetcher = NewsFetcher()
