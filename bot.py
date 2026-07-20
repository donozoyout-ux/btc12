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

from src.config import settings
from src.trader import trader
from src.executor import executor
from src.quant_agent import quant_agent
from src.analyzer import analyzer
from src.news import news_fetcher
from src.database import db
from src import supabase_store
from src import self_improve

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


def get_technical_indicators(symbol: str = "BTC/USDT", timeframe: str = "5m", limit: int = 100):
    """Hem 5m hem 1h verilerini çek ve analiz et"""
    try:
        # 5m timeframe
        ohlcv_5m = trader.get_bars(limit=limit, timeframe=timeframe)
        teknik_5m = analyzer.analyze(ohlcv_5m) if ohlcv_5m is not None and len(ohlcv_5m) >= 50 else None
        
        # 1h timeframe (higher timeframe context)
        ohlcv_1h = trader.get_bars(limit=100, timeframe='1h')
        teknik_1h = analyzer.analyze(ohlcv_1h) if ohlcv_1h is not None and len(ohlcv_1h) >= 50 else None
        
        # Orderbook verisi
        orderbook = trader.get_orderbook()
        
        # Birincil analiz (5m)
        if teknik_5m:
            teknik_5m["orderbook"] = orderbook
            if teknik_1h:
                teknik_5m["htf_trend"] = teknik_1h.get("ema_cross", "unknown")
                teknik_5m["htf_rsi"] = teknik_1h.get("rsi", 50)
        
        return teknik_5m, teknik_1h
    except Exception as e:
        logger.error(f"Technical analysis failed: {e}")
        return None, None


def get_news_sentiment():
    """Haberleri çek ve sentiment analizi yap"""
    try:
        haberler = news_fetcher.fetch_bitcoin_news(limit=5)
        return haberler
    except Exception as e:
        logger.warning(f"News fetch failed: {e}")
        return [{"baslik": "Harici haber kaynagi baglanamadi", "sentiment": "notr"}]


def get_portfolio():
    """Gerçek portföy verilerini getir"""
    try:
        account = executor.get_account()
        position = executor.get_position()
        
        return {
            "usdt_bakiye": account.get("cash", 0.0),
            "btc_bakiye": account.get("btc", 0.0),
            "acik_pozisyon": position is not None,
            "giris_fiyati": position.get("avg_entry_price", 0.0) if position else 0.0,
            "pozisyon_degeri": position.get("market_value", 0.0) if position else 0.0,
            "kar_zarar": position.get("unrealized_pl", 0.0) if position else 0.0,
        }
    except Exception as e:
        logger.error(f"Portfolio fetch failed: {e}")
        return {
            "usdt_bakiye": 0.0,
            "btc_bakiye": 0.0,
            "acik_pozisyon": False,
            "giris_fiyati": 0.0,
            "pozisyon_degeri": 0.0,
            "kar_zarar": 0.0,
        }


def execute_trade(decision: dict, portfolio: dict, current_price: float):
    """Executor ile trade'i gerçekleştir"""
    action = decision["action"]
    if action == "HOLD":
        return

    exec_p = decision["execution"]
    size_pct = exec_p.get("size_percentage", 100)
    amount_usd = exec_p.get("amount_usd", None)
    sl = exec_p.get("stop_loss", 0.0)
    tp = exec_p.get("take_profit", 0.0)

    if action == "BUY":
        if executor.get_position() is not None:
            logger.warning("Zaten açık pozisyon var, alım atlanıyor")
            return
        logger.info(f"BUY emri gonderiliyor... Size: {size_pct}%, Amount: ${amount_usd or settings.position_size_usd}")
        result = executor.buy(size_pct=size_pct, amount_usd=amount_usd)
        if result:
            db.save_trade("BUY", result["price"], result["qty"], 0, decision.get("system_log", ""), result["price"], result.get("mode", "REAL"), result.get("fee", 0))
            logger.info(f"ALIS BASARILI: {result}")
        else:
            logger.error("ALIS BASARISIZ")

    elif action == "SELL":
        pos = executor.get_position()
        if not pos or pos.get("qty", 0) <= 0:
            logger.warning("Satılacak BTC yok")
            return
        logger.info(f"SELL emri gonderiliyor... Pozisyon: {pos['qty']} BTC")
        result = executor.sell()
        if result:
            pnl = result.get("pl", 0.0)
            fee = result.get("fee", 0.0)
            gross = result.get("gross", 0.0)
            db.save_trade("SELL", result["price"], result["qty"], pnl, decision.get("system_log", ""), pos.get("avg_entry_price", 0), result.get("mode", "REAL"), fee)
            # QuantAgent'e sonucu bildir
            quant_agent.islem_sonucu_kaydet(pnl)
            logger.info(f"SATIS BASARILI: {result} | PNL: ${pnl:+.2f} | Komisyon: ${fee:+.2f} (brüt: ${gross:.2f})")

    # İşlem kapandıysa (BUY/SELL) adaptasyon sayacını ilerlet (periyodik
    # review_and_adapt zaten scan döngüsünde her 50 taramada çalışır)
    if action in ("BUY", "SELL"):
        self_improve.note_trade_closed()


def main():
    logger.info(f"Bot started | Symbol: {settings.symbol} | Mode: {settings.executor_mode.upper()} | Testnet: {settings.binance_testnet}")

    while True:
        try:
            logger.info("--- New analysis cycle ---")

            # Teknik analiz
            teknik, teknik_1h = get_technical_indicators()
            if not teknik:
                logger.warning("Technical data unavailable -> HOLD")
                time.sleep(settings.check_interval)
                continue

            price = teknik["price"]
            
            # Haberler
            haberler = get_news_sentiment()
            
            # Portföy
            portfoy = get_portfolio()
            
            # Geçmiş hafıza
            memory = load_json(MEMORY_FILE, dict(DEFAULT_MEMORY))

            logger.info(f"Price: {price} | RSI: {teknik['rsi']} | EMA: {teknik['ema_cross']} | Portfolio: {portfoy['usdt_bakiye']:.2f} USDT / {portfoy['btc_bakiye']:.6f} BTC")

            # QuantAgent analizi (5 ajan konsensüs + XGBoost + Sermaye Yönetimi)
            decision = quant_agent.analyze(teknik, haberler, portfoy, memory)

            logger.info(f"Decision: {decision['action']} | Confidence: {decision['confidence_score']}")

            # Trade'i execute et
            if decision["action"] in ("BUY", "SELL"):
                execute_trade(decision, portfoy, price)

            # Memory güncelle
            memory = load_json(MEMORY_FILE, dict(DEFAULT_MEMORY))
            mu = decision.get("memory_update", {})
            if mu.get("aktif_strateji_notu"):
                memory["aktif_strateji_notu"] = mu["aktif_strateji_notu"]
            if mu.get("risk_seviyesi_ayari"):
                memory["risk_seviyesi_ayari"] = mu["risk_seviyesi_ayari"]
            if decision.get("system_log"):
                memory.setdefault("son_hatalar", []).append(decision["system_log"])
                memory["son_hatalar"] = memory["son_hatalar"][-5:]
            save_json(MEMORY_FILE, memory)

            logger.info(f"Sleeping {settings.check_interval}s until next cycle...")
            time.sleep(settings.check_interval)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            sys.exit(0)
        except Exception as e:
            logger.critical(f"Unhandled error: {e}\n{traceback.format_exc()}")
            memory = load_json(MEMORY_FILE, dict(DEFAULT_MEMORY))
            memory.setdefault("son_hatalar", []).append(str(e))
            memory["son_hatalar"] = memory["son_hatalar"][-5:]
            save_json(MEMORY_FILE, memory)
            time.sleep(30)


if __name__ == "__main__":
    main()
