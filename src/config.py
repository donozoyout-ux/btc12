import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    binance_api_key = os.getenv("BINANCE_API_KEY", "")
    binance_secret_key = os.getenv("BINANCE_SECRET_KEY", "")
    binance_testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    symbol = "BTC/USDT"
    check_interval = int(os.getenv("CHECK_INTERVAL", "15"))
    position_size_usd = float(os.getenv("POSITION_SIZE_USD", "500"))
    risk_per_trade = float(os.getenv("RISK_PER_TRADE", "2"))
    rr_ratio = float(os.getenv("RR_RATIO", "2"))
    max_consecutive_losses = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))

    executor_mode = os.getenv("EXECUTOR_MODE", "binance")
    stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "3"))
    last_entry_price = 0
    memory_file = "state.json"


settings = Settings()

# Startup kontrol
if not settings.telegram_bot_token or not settings.telegram_chat_id:
    print("[CONFIG] UYARI: Telegram API anahtarlari eksik!")
if settings.executor_mode == "binance":
    if not settings.binance_api_key or not settings.binance_secret_key:
        print("[CONFIG] UYARI: Binance API anahtarlari eksik! EXECUTOR_MODE=binance ama key yok.")
        print("[CONFIG] Render'da Environment Variables ayarlayin:")
        print("[CONFIG]   BINANCE_API_KEY = ...")
        print("[CONFIG]   BINANCE_SECRET_KEY = ...")
    else:
        print(f"[CONFIG] Binance API anahtarlari mevcut, testnet={settings.binance_testnet} ile baglanilacak")
