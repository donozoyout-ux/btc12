import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # Alpaca
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    alpaca_base_url: str = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Trading
    symbols: list = None
    timeframe: str = os.getenv("TIMEFRAME", "1Min")
    check_interval: int = int(os.getenv("CHECK_INTERVAL", "120"))

    def __post_init__(self):
        if self.symbols is None:
            default = "BTC/USD,ETH/USD,SOL/USD,XRP/USD,DOGE/USD,ADA/USD,AVAX/USD"
            symbols_str = os.getenv("SYMBOLS", default)
            seen = set()
            result = []
            for s in symbols_str.split(","):
                s = s.strip()
                if s and s not in seen and s.endswith("/USD"):
                    seen.add(s)
                    result.append(s)
            self.symbols = result

    # Strategy - 5% gunluk hedef icin daha agresif
    rsi_period: int = int(os.getenv("RSI_PERIOD", "14"))
    rsi_overbought: int = int(os.getenv("RSI_OVERBOUGHT", "65"))
    rsi_oversold: int = int(os.getenv("RSI_OVERSOLD", "35"))
    bb_period: int = int(os.getenv("BB_PERIOD", "20"))
    bb_std: float = float(os.getenv("BB_STD", "2.0"))
    volume_spike_multiplier: float = float(os.getenv("VOLUME_SPIKE_MULTIPLIER", "1.5"))
    price_change_threshold: float = float(os.getenv("PRICE_CHANGE_THRESHOLD", "0.015"))

    # Risk - 5% gunluk hedef icin
    position_size_usd: float = float(os.getenv("POSITION_SIZE_USD", "200"))
    max_positions: int = int(os.getenv("MAX_POSITIONS", "3"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.015"))
    take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "0.04"))

    def validate(self) -> list[str]:
        errors = []
        if not self.alpaca_api_key:
            errors.append("ALPACA_API_KEY not set")
        if not self.alpaca_secret_key:
            errors.append("ALPACA_SECRET_KEY not set")
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN not set")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID not set")
        return errors


settings = Settings()