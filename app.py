import sys
sys.path.insert(0, '.')

if __name__ == '__main__':
    from src.panel import app, setup_telegram
    import os

    print("[SYSTEM] BTC Bot baslatiliyor...")
    setup_telegram()

    port = int(os.environ.get('PORT', 5000))
    print(f"[PANEL] http://0.0.0.0:{port}")

    app.run(host='0.0.0.0', port=port, debug=False)
