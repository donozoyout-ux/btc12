import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    alpaca_api_key = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    alpaca_base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    symbols = ["BTC/USD", "ETH/USD"]

    check_interval = int(os.getenv("CHECK_INTERVAL", "120"))
    position_size_usd = float(os.getenv("POSITION_SIZE_USD", "100"))
    stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "0.012"))
    take_profit_pct = float(os.getenv("TAKE_PROFIT_PCT", "0.025"))
    min_confidence = float(os.getenv("MIN_CONFIDENCE", "0.35"))

    memory_file = os.getenv("MEMORY_FILE", "trades.json")
    activity_log_file = os.getenv("ACTIVITY_LOG", "activity.json")

    def validate(self):
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
