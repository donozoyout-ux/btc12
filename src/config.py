import os
from dotenv import load_dotenv

load_dotenv(override=True)


class Settings:
    binance_api_key = os.getenv("BINANCE_API_KEY", "")
    binance_secret_key = os.getenv("BINANCE_SECRET_KEY", "")
    binance_testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    symbol = os.getenv("SYMBOL", "BTC/USDT")
    # ─── Ücretsiz LLM (Groq / OpenAI-uyumlu) ───
    # 5-beyinli LLM tartişmasi bu anahtarla çalişir. Ücretsiz (kart yok):
    # console.groq.com/keys  ->  LLM_MODEL=llama-3.3-70b-versatile
    llm_api_key = os.getenv("LLM_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    llm_base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    llm_model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    # LLM tartişmasinin konsensüsteki ağirlği (0 = devre dişi, 1 = tam ajan gibi)
    llm_weight = float(os.getenv("LLM_WEIGHT", os.getenv("GEMINI_WEIGHT", "1.0")))
    check_interval = int(os.getenv("CHECK_INTERVAL", "10"))
    position_size_usd = float(os.getenv("POSITION_SIZE_USD", "500"))
    risk_per_trade = float(os.getenv("RISK_PER_TRADE", "2"))
    rr_ratio = float(os.getenv("RR_RATIO", "2"))
    max_consecutive_losses = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))

    # Varsayilan: sim (gercek islem acilmaz). Gercek Binance islemi icin
    # asagidaki degeri "binance" yapip API anahtari vermen gerekir.
    executor_mode = os.getenv("EXECUTOR_MODE", "sim")
    stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "3"))
    last_entry_price = 0
    memory_file = "state.json"

    # ─── Scalping / Day Trading (M10–M30) ayarlari ───
    # Indikatorlerin beslenecegi kisa vadeli periyotlar.
    scalp_timeframes = os.getenv("SCALP_TIMEFRAMES", "5m,10m,15m").split(",")
    # SL/TP hesabinda ATR'a gore dinamik kat sayilar (kisa vade => dar).
    scalp_sl_atr_mult = float(os.getenv("SCALP_SL_ATR_MULT", "1.0"))
    scalp_tp_atr_mult = float(os.getenv("SCALP_TP_ATR_MULT", "1.8"))
    # Guvenlik cap'i: ATR asiri buyukse bile SL/TP bu yuzdeyi asamaz.
    scalp_max_sl_pct = float(os.getenv("SCALP_MAX_SL_PCT", "0.6"))
    scalp_max_tp_pct = float(os.getenv("SCALP_MAX_TP_PCT", "1.2"))
    # Trailing (kademeli SL) baslatma esigi (kisa vadede erken kilit).
    scalp_trailing_trigger_pct = float(os.getenv("SCALP_TRAILING_TRIGGER_PCT", "0.5"))

    # Scalping modunda kısmi uyuşma ile de işlem açılabilsin (varsayılan 2/5)
    consensus_min = int(os.getenv("CONSENSUS_MIN", "2"))

    # Aç gözlülük / atak modu: kapalıyken sistem disiplinli ve sabırlı kalır,
    # işlem agresifliğini otomatik artırmaz, günlük sabit hedef peşinde koşmaz.
    aggressive_mode = os.getenv("AGGRESSIVE_MODE", "true").lower() == "true"
    # Günlük hedef (%). 0 = hedef yok (sadece risk yönetimi). >0 ise gerisindeyken
    # daha sabırlı olunur, asla "daha atak" davranılmaz.
    daily_goal_pct = float(os.getenv("DAILY_GOAL_PCT", "1"))
    # Simülasyon başlangıç sermayesi — TRY (₺) cinsinden. Sistem içi
    # hesaplamalar USD üzerinden yürür; bu değer canlı USD/TRY kuruyla
    # USD'ye çevrilir. Varsayılan: 500 ₺.
    sim_starting_capital_tl = float(os.getenv("SIM_STARTING_CAPITAL_TL", "500"))
    # Geriye dönük uyum için USD tabanlı eski alan (varsayılan 500 USD fallback).
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
    print("[CONFIG] UYARI: Telegram API anahtarlari eksik! (opsiyonel)")
if settings.executor_mode == "binance":
    print("[CONFIG] UYARI: EXECUTOR_MODE=binance ama Binance hesabi kaldirildi.")
    print("[CONFIG] Simulasyon moduna geciliyor (sahte para, canli veri CoinGecko).")
    settings.executor_mode = "sim"
else:
    print(f"[CONFIG] MOD: SIMULASYON (gercek islem YOK, sahte para). Baslangic sermaye: ₺{settings.sim_starting_capital_tl:.0f}")
    print("[CONFIG] Canli veri kaynagi: CoinGecko -> sentetik fallback")
