import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    exchange_api_key = os.getenv("EXCHANGE_API_KEY", "")
    exchange_secret_key = os.getenv("EXCHANGE_SECRET_KEY", "")
    exchange_name = os.getenv("EXCHANGE_NAME", "binance")

    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    symbol = "BTC/USDT"
    check_interval = int(os.getenv("CHECK_INTERVAL", "60"))
    position_size_usd = float(os.getenv("POSITION_SIZE_USD", "50"))
    daily_profit_target = float(os.getenv("DAILY_PROFIT_TARGET", "25"))
    last_entry_price = 0

    executor_mode = os.getenv("EXECUTOR_MODE", "dry_run")

    alpaca_api_key = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    alpaca_base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "3"))

    memory_file = os.getenv("MEMORY_FILE", "trades.json")

    def validate(self):
        errors = []
        if not self.deepseek_api_key:
            errors.append("DEEPSEEK_API_KEY not set")
        if not self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN not set")
        if not self.telegram_chat_id:
            errors.append("TELEGRAM_CHAT_ID not set")
        if self.executor_mode == "alpaca":
            if not self.alpaca_api_key:
                errors.append("ALPACA_API_KEY required for alpaca mode")
            if not self.alpaca_secret_key:
                errors.append("ALPACA_SECRET_KEY required for alpaca mode")
        return errors


settings = Settings()
