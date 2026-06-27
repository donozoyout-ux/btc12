import sys
sys.path.insert(0, '.')

from src.config import settings
from src.alpaca_client import AlpacaClient


def test_setup():
    print("[*] Testing configuration...")
    errors = settings.validate()
    if errors:
        print("[X] Configuration errors:")
        for e in errors:
            print(f"   - {e}")
        print("\n[!] Please edit .env file with your credentials")
        return False

    print("[OK] Configuration valid")

    print("\n[*] Testing Alpaca connection...")
    try:
        client = AlpacaClient()
        account = client.get_account()
        print(f"[OK] Connected!")
        print(f"   Account: {account.id}")
        print(f"   Status: {account.status}")
        print(f"   Buying Power: ${float(account.buying_power):,.2f}")
        print(f"   Portfolio Value: ${float(account.portfolio_value):,.2f}")

        clock = client.get_clock()
        print(f"   Market Open: {clock.is_open}")

        print("\n[*] Testing market data...")
        df = client.get_bars(limit=20)
        if not df.empty:
            latest = df.iloc[-1]
            print(f"   Latest BTC: ${latest['close']:,.2f}")
            print(f"   Volume: {latest['volume']:,.0f}")
        else:
            print("   [!] No market data (market may be closed)")

        print("\n[*] Current positions:")
        positions = client.get_positions()
        if positions:
            for p in positions:
                print(f"   {p['symbol']}: {p['qty']} @ ${p['avg_entry_price']:,.2f} (P/L: ${p['unrealized_pl']:+,.2f})")
        else:
            print("   No open positions")

        print("\n[OK] All tests passed! Ready to run bot.")
        return True

    except Exception as e:
        print(f"[X] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_setup()