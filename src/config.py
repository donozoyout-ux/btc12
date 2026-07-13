import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    binance_api_key = os.getenv("BINANCE_API_KEY", "")
    binance_secret_key = os.getenv("BINANCE_SECRET_KEY", "")
    binance_testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    symbol = os.getenv("SYMBOL", "BTC/USDT")
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    check_interval = int(os.getenv("CHECK_INTERVAL", "15"))
    position_size_usd = float(os.getenv("POSITION_SIZE_USD", "500"))
    risk_per_trade = float(os.getenv("RISK_PER_TRADE", "2"))
    rr_ratio = float(os.getenv("RR_RATIO", "2"))
    max_consecutive_losses = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))

    executor_mode = os.getenv("EXECUTOR_MODE", "binance")
    stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "3"))
    last_entry_price = 0
    memory_file = "state.json"

    # Gemini 5-Brain konsensüs ağırlığı (0 = devre dışı, 1 = tam ajan gibi sayılır)
    gemini_weight = float(os.getenv("GEMINI_WEIGHT", "1.0"))

    # Aç gözlülük / atak modu: kapalıyken sistem disiplinli ve sabırlı kalır,
    # işlem agresifliğini otomatik artırmaz, günlük sabit hedef peşinde koşmaz.
    aggressive_mode = os.getenv("AGGRESSIVE_MODE", "false").lower() == "true"
    # Günlük hedef (%). 0 = hedef yok (sadece risk yönetimi). >0 ise gerisindeyken
    # daha sabırlı olunur, asla "daha atak" davranılmaz.
    daily_goal_pct = float(os.getenv("DAILY_GOAL_PCT", "0"))
    # Simülasyon başlangıç sermayesi (kullanıcı ayarlayabilir)
    sim_starting_capital = float(os.getenv("SIM_STARTING_CAPITAL", "500"))
    binance_proxy = os.getenv("BINANCE_PROXY", "")
    binance_api_url = os.getenv("BINANCE_API_URL", "")

    @property
    def base_asset(self):
        return self.symbol.split('/')[0] if '/' in self.symbol else 'BTC'

    @property
    def quote_asset(self):
        return self.symbol.split('/')[1] if '/' in self.symbol else 'USDT'


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
        mode = "LIVE" if not settings.binance_testnet else "TESTNET"
        print(f"[CONFIG] Binance API anahtarlari mevcut, {mode} modunda baglanilacak")
