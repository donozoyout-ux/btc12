import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    alpaca_api_key = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    alpaca_base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    symbol = "BTC/USDT"
    check_interval = int(os.getenv("CHECK_INTERVAL", "300"))
    position_size_usd = float(os.getenv("POSITION_SIZE_USD", "50"))
    risk_per_trade = float(os.getenv("RISK_PER_TRADE", "2"))
    rr_ratio = float(os.getenv("RR_RATIO", "2"))
    max_consecutive_losses = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))

    executor_mode = os.getenv("EXECUTOR_MODE", "alpaca")
    stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "3"))
    last_entry_price = 0
    memory_file = "state.json"


settings = Settings()
