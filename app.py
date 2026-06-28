import sys
sys.path.insert(0, '.')

if __name__ == '__main__':
    from src.panel import app, bot, settings, setup_telegram
    from src.telegram import tg
    import os

    errors = settings.validate()
    if errors:
        for e in errors:
            print(f"[WARN] {e}")

    print("=" * 50)
    print("CRYPTO AI BOT - BTC & ETH Scanner")
    print("=" * 50)

    setup_telegram()
    print("[OK] Telegram dinleniyor...")

    port = int(os.environ.get('PORT', 5000))
    print(f"[OK] Panel: http://0.0.0.0:{port}")
    print(f"[OK] Coin: {', '.join(settings.symbols)}")
    print(f"[OK] Islem: ${settings.position_size_usd}")
    print(f"[OK] SL: %{settings.stop_loss_pct*100:.1f}  TP: %{settings.take_profit_pct*100:.1f}")

    tg.send(
        f"<b>SISTEM HAZIR</b>\n\n"
        f"Coin: BTC, ETH\n"
        f"Islem: ${settings.position_size_usd}\n\n"
        f"Basla: <code>/start</code>\n"
        f"Komutlar: <code>/help</code>"
    )

    app.run(host='0.0.0.0', port=port, debug=False)
