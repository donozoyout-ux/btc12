import os
import sys
import json
import time
import logging
import traceback
from datetime import datetime
from pathlib import Path

import ccxt
import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"
MEMORY_FILE = "memory.json"

DEFAULT_MEMORY = {
    "son_islem_kar_zarar": 0.0,
    "son_hatalar": [],
    "aktif_strateji_notu": "Initial state - no trades yet",
    "ardisik_kar_sayisi": 0,
    "ardisik_zarar_sayisi": 0,
    "toplam_islem_sayisi": 0,
    "toplam_kar_zarar": 0.0,
    "risk_seviyesi_ayari": "normal",
}

LLM_SYSTEM_PROMPT = """You are a Quantitative Trading & Portfolio Management Agent for BTC/USDT.
Your ONLY output must be valid JSON matching this schema:
{
    "action": "BUY" | "CLOSE" | "HOLD",
    "confidence_score": 0.0,
    "execution": {
        "size_percentage": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0
    },
    "memory_update": {
        "aktif_strateji_notu": "market note for next cycle",
        "risk_seviyesi_ayari": "normal" | "muhafazakar"
    },
    "system_log": ""
}

Rules:
- If acik_pozisyon is false and conditions favor a long, output BUY with target_entry, stop_loss, take_profit as exact prices.
- If acik_pozisyon is true, compare current price to stop_loss/take_profit. If hit, output CLOSE.
- If consecutive losses in memory, raise confidence threshold and be more selective.
- If data is incomplete or API error, output HOLD and note in system_log.
- Never output anything outside this JSON. No explanation, no markdown."""


def load_json(filepath: str, default=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Cannot load {filepath}: {e}. Using default.")
        return default if default is not None else {}


def save_json(filepath: str, data: dict):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save {filepath}: {e}")


def init_exchange(config: dict):
    exchange_name = config.get("exchange", {}).get("name", "binance")
    api_key = os.getenv("EXCHANGE_API_KEY") or config.get("exchange", {}).get("api_key", "")
    secret = os.getenv("EXCHANGE_SECRET") or config.get("exchange", {}).get("secret", "")
    is_paper = config.get("exchange", {}).get("paper", False)

    if not api_key or not secret:
        logger.warning("Exchange API keys not configured. Running in PAPER mode.")
        return None

    try:
        exchange_class = getattr(ccxt, exchange_name)
        exchange_params = {
            "apiKey": api_key,
            "secret": secret,
            "options": {"defaultType": "spot"},
            "enableRateLimit": True,
        }

        if exchange_name == "alpaca":
            trader_url = "https://paper-api.alpaca.markets" if is_paper else "https://api.alpaca.markets"
            exchange_params["urls"] = {
                "api": {
                    "trader": trader_url,
                    "market": "https://data.alpaca.markets",
                }
            }
            mode = "paper" if is_paper else "live"
            logger.info(f"Alpaca {mode} trading mode enabled")

        exchange = exchange_class(exchange_params)
        exchange.load_markets()
        logger.info(f"Connected to {exchange_name}")
        return exchange
    except Exception as e:
        logger.error(f"Exchange init failed: {e}")
        return None


def get_technical_indicators(exchange, symbol: str, timeframe: str = "1h", limit: int = 100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        current_price = float(df["close"].iloc[-1])
        rsi = float(RSIIndicator(close=df["close"], window=14).rsi().iloc[-1])

        ema12 = float(EMAIndicator(close=df["close"], window=12).ema_indicator().iloc[-1])
        ema26 = float(EMAIndicator(close=df["close"], window=26).ema_indicator().iloc[-1])
        ema_cross = "bullish" if ema12 > ema26 else "bearish"

        avg_vol = float(df["volume"].tail(20).mean())
        cur_vol = float(df["volume"].iloc[-1])
        if cur_vol > avg_vol * 1.5:
            hacim = "yuksek"
        elif cur_vol > avg_vol * 0.8:
            hacim = "normal"
        else:
            hacim = "dusuk"

        recent_high = float(df["high"].tail(50).max())
        recent_low = float(df["low"].tail(50).min())
        support = recent_low
        resistance = recent_high

        return {
            "fiyat": round(current_price, 2),
            "rsi": round(rsi, 2),
            "ema_cross": ema_cross,
            "hacim": hacim,
            "ema12": round(ema12, 2),
            "ema26": round(ema26, 2),
            "son_20_hacim_ort": round(avg_vol, 2),
            "destek_seviyesi": round(support, 2),
            "direnc_seviyesi": round(resistance, 2),
        }
    except Exception as e:
        logger.error(f"Technical analysis failed: {e}")
        return None


def get_news_sentiment(config: dict):
    news_list = []
    api_key = os.getenv("NEWS_API_KEY") or config.get("news", {}).get("api_key", "")

    if api_key:
        try:
            source = config.get("news", {}).get("source", "cryptopanic")
            if source == "cryptopanic":
                resp = requests.get(
                    "https://cryptopanic.com/api/v1/posts/",
                    params={"auth_token": api_key, "currencies": "BTC", "kind": "news"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for post in data.get("results", [])[:5]:
                        title = post.get("title", "")
                        votes = post.get("votes", {})
                        positive = votes.get("positive", 0)
                        negative = votes.get("negative", 0)
                        if positive > negative:
                            sentiment = "pozitif"
                        elif negative > positive:
                            sentiment = "negatif"
                        else:
                            sentiment = "notr"
                        news_list.append({"baslik": title, "sentiment": sentiment})
        except Exception as e:
            logger.warning(f"News fetch failed: {e}")

    if not news_list:
        news_list.append({"baslik": "Harici haber kaynagi baglanamadi", "sentiment": "notr"})

    return news_list


def get_portfolio(exchange, symbol: str):
    empty = {"usdt_bakiye": 0.0, "btc_bakiye": 0.0, "acik_pozisyon": False, "giris_fiyati": 0.0}
    if not exchange:
        return empty

    try:
        balance = exchange.fetch_balance()
        usdt = float(balance.get("USDT", {}).get("free", 0.0))
        btc = float(balance.get("BTC", {}).get("free", 0.0))

        orders = exchange.fetch_open_orders(symbol)
        acik = len(orders) > 0
        giris = 0.0
        if acik and orders[0].get("price"):
            giris = float(orders[0]["price"])

        return {
            "usdt_bakiye": round(usdt, 2),
            "btc_bakiye": round(btc, 8),
            "acik_pozisyon": acik,
            "giris_fiyati": round(giris, 2),
        }
    except Exception as e:
        logger.error(f"Portfolio fetch failed: {e}")
        return empty


def call_llm(config: dict, user_prompt: str) -> dict:
    api_key = os.getenv("LLM_API_KEY") or config.get("llm", {}).get("api_key", "")
    api_url = config.get("llm", {}).get(
        "api_url", "https://api.deepseek.com/v1/chat/completions"
    )
    model = config.get("llm", {}).get("model", "deepseek-chat")

    if not api_key:
        logger.error("LLM API key not configured")
        return default_hold_decision("LLM API anahtari eksik")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 600,
    }

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        if content.startswith("```json"):
            content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        decision = json.loads(content)
        validate_decision(decision)
        return decision
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return default_hold_decision(f"LLM cagi hatasi: {str(e)}")


def validate_decision(decision: dict):
    assert "action" in decision and decision["action"] in ("BUY", "CLOSE", "HOLD")
    assert "confidence_score" in decision and 0.0 <= decision["confidence_score"] <= 1.0
    assert "execution" in decision
    assert "memory_update" in decision
    assert "system_log" in decision


def default_hold_decision(reason: str) -> dict:
    return {
        "action": "HOLD",
        "confidence_score": 0.0,
        "execution": {"size_percentage": 0.0, "stop_loss": 0.0, "take_profit": 0.0},
        "memory_update": {
            "aktif_strateji_notu": f"HOLD due to error: {reason}",
            "risk_seviyesi_ayari": "muhafazakar",
        },
        "system_log": reason,
    }


def execute_trade(exchange, decision: dict, portfolio: dict, current_price: float, config: dict):
    action = decision["action"]
    if action == "HOLD":
        return

    exec_p = decision["execution"]
    size_pct = exec_p.get("size_percentage", 0.0)
    sl = exec_p.get("stop_loss", 0.0)
    tp = exec_p.get("take_profit", 0.0)

    min_notional = config.get("trading", {}).get("min_notional_usdt", 10)

    if action == "BUY":
        usdt = portfolio.get("usdt_bakiye", 0.0)
        amt_usdt = usdt * (size_pct / 100.0)
        if amt_usdt < min_notional:
            logger.warning(f"Trade too small: {amt_usdt:.2f} USDT < {min_notional}")
            return
        btc_amt = amt_usdt / current_price
        logger.info(f"BUY {btc_amt:.6f} BTC @ {current_price:.2f} | SL: {sl:.2f} TP: {tp:.2f}")

        if exchange:
            try:
                order = exchange.create_market_buy_order("BTC/USDT", btc_amt)
                logger.info(f"Buy executed: {order.get('id')}")
            except Exception as e:
                logger.error(f"Buy failed: {e}")

    elif action == "CLOSE":
        btc = portfolio.get("btc_bakiye", 0.0)
        if btc <= 0:
            logger.warning("No BTC to sell")
            return
        logger.info(f"CLOSE {btc:.6f} BTC @ {current_price:.2f}")
        if exchange:
            try:
                order = exchange.create_market_sell_order("BTC/USDT", btc)
                logger.info(f"Sell executed: {order.get('id')}")
            except Exception as e:
                logger.error(f"Sell failed: {e}")


def build_user_prompt(tek_analiz: dict, haberler: list, portfoy: dict, memory: dict) -> str:
    data = {
        "teknik_analiz": tek_analiz,
        "internet_ve_haberler": haberler,
        "mevcut_portfoy": portfoy,
        "gecmis_hafiza": memory,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def main():
    config = load_json(CONFIG_FILE, {})
    if not config:
        logger.error("config.json bulunamadi.")
        sys.exit(1)

    exchange = init_exchange(config)
    symbol = config.get("exchange", {}).get("symbol", "BTC/USDT")
    timeframe = config.get("exchange", {}).get("timeframe", "1h")
    sleep_sec = config.get("trading", {}).get("sleep_hours", 1) * 3600
    cooldown = config.get("trading", {}).get("cooldown_after_error", 30)

    logger.info(f"Bot started | Symbol: {symbol} | Timeframe: {timeframe}")

    while True:
        try:
            logger.info("--- New analysis cycle ---")

            tek = get_technical_indicators(exchange, symbol, timeframe)
            if not tek:
                logger.warning("Technical data unavailable -> HOLD")
                decision = default_hold_decision("Teknik veri alinamadi")
            else:
                price = tek["fiyat"]
                haber = get_news_sentiment(config)
                portfoy = get_portfolio(exchange, symbol)
                memory = load_json(MEMORY_FILE, dict(DEFAULT_MEMORY))

                logger.info(f"Price: {price} | RSI: {tek['rsi']} | EMA: {tek['ema_cross']} | Portfolio: {portfoy['usdt_bakiye']:.2f} USDT / {portfoy['btc_bakiye']:.6f} BTC")

                prompt = build_user_prompt(tek, haber, portfoy, memory)
                decision = call_llm(config, prompt)

            logger.info(f"Decision: {decision['action']} | Confidence: {decision['confidence_score']}")

            if exchange and decision["action"] in ("BUY", "CLOSE"):
                price_cur = (exchange.fetch_ticker(symbol)["last"] if exchange else 0)
                portfoy = get_portfolio(exchange, symbol)
                execute_trade(exchange, decision, portfoy, price_cur, config)

            memory = load_json(MEMORY_FILE, dict(DEFAULT_MEMORY))
            mu = decision.get("memory_update", {})
            if mu.get("aktif_strateji_notu"):
                memory["aktif_strateji_notu"] = mu["aktif_strateji_notu"]
            if mu.get("risk_seviyesi_ayari"):
                memory["risk_seviyesi_ayari"] = mu["risk_seviyesi_ayari"]
            if decision.get("system_log"):
                memory["son_hatalar"] = memory.get("son_hatalar", [])
                memory["son_hatalar"].append(decision["system_log"])
                memory["son_hatalar"] = memory["son_hatalar"][-5:]
            save_json(MEMORY_FILE, memory)

            logger.info(f"Sleeping {sleep_sec}s until next cycle...")
            time.sleep(sleep_sec)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            sys.exit(0)
        except Exception as e:
            logger.critical(f"Unhandled error: {e}\n{traceback.format_exc()}")
            memory = load_json(MEMORY_FILE, dict(DEFAULT_MEMORY))
            memory.setdefault("son_hatalar", []).append(str(e))
            memory["son_hatalar"] = memory["son_hatalar"][-5:]
            save_json(MEMORY_FILE, memory)
            logger.info(f"Cooldown {cooldown}s...")
            time.sleep(cooldown)


if __name__ == "__main__":
    main()
