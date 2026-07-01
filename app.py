import sys
sys.path.insert(0, '.')

if __name__ == '__main__':
    from src.panel import app, setup_telegram
    from src.bot import bot
    from src.config import settings
    import os

    print("[SYSTEM] BTC Bot baslatiliyor...")
    setup_telegram()

    print("[SISTEM] Bot otomatik baslatiliyor...")
    bot.start(mesaj_gonder=True)

    port = int(os.environ.get('PORT', 5000))
    print(f"[PANEL] http://0.0.0.0:{port}")
    print(f"[BOT] Tarama araligi: {settings.check_interval}s")

    app.run(host='0.0.0.0', port=port, debug=False)
