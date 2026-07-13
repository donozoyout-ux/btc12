"""Analitik / matematiksel performans katmani.

Tum metrikler `trades` tablosundaki KAPALI islemlerden (action='SELL', pnl!=0)
turetilir. Formuller acik sekilde tanimlanir; "kafaya gore" degil, sayisaldir.
"""


from src.config import settings
from src import self_improve


def _closed_trades(trades):
    """Kapanmis (SELL) ve pnl degeri olan islemleri dondurur."""
    return [t for t in trades if t.get("action") == "SELL" and t.get("pnl") is not None]


def compute_stats(trades, starting_capital=None):
    """Kapanmis islemler uzerinden temel istatistiksel metrikleri hesaplar."""
    closed = _closed_trades(trades)
    n = len(closed)
    if n == 0:
        return {
            "total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "expectancy": 0.0,
            "profit_factor": 0.0, "avg_r": 0.0, "max_drawdown": 0.0,
            "total_pnl": 0.0,
        }

    wins = [t["pnl"] for t in closed if t["pnl"] > 0]
    losses = [t["pnl"] for t in closed if t["pnl"] < 0]
    w, l = len(wins), len(losses)
    total = w + l
    win_rate = w / total if total else 0.0
    avg_win = sum(wins) / w if w else 0.0
    avg_loss = sum(losses) / l if l else 0.0
    total_pnl = sum(t["pnl"] for t in closed)

    # Beklenti (Expectancy):
    #   E = P(kazanma) * ort_kar - P(kaybetme) * |ort_zarar|
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0

    # R-multiple: SL otomatik kapali oldugu icin maliyet bazli R analizi
    # burada yapilmaz; 0 birakilir (gelecekte entry/SL ile zenginlestirilebilir).
    avg_r = 0.0

    eq = equity_curve(trades, starting_capital or settings.sim_starting_capital)
    max_dd = _max_drawdown(eq)

    return {
        "total": total, "wins": w, "losses": l, "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_r": round(avg_r, 2), "max_drawdown": round(max_dd, 4),
        "total_pnl": round(total_pnl, 2),
    }


def equity_curve(trades, starting_capital):
    """Kapanmis islemlerin kümülatif K/Z'iyla portföy degerini döndürür (list[float])."""
    closed = _closed_trades(trades)
    eq = [float(starting_capital)]
    for t in closed:
        eq.append(eq[-1] + float(t.get("pnl", 0) or 0))
    return eq


def _max_drawdown(equity):
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        if dd > mdd:
            mdd = dd
    return mdd


def position_size_rationale(equity, confidence, win_rate=0.5, drawdown_pct=0.0, daily_progress=0.0):
    """Dinamik islem boyutunun NEDEN o secildigini analitik olarak aciklar."""
    amount = self_improve.decide_position_size(
        equity, confidence, win_rate, drawdown_pct, daily_progress
    )
    risk_pct = (amount / equity * 100) if equity > 0 else 0.0
    return {
        "amount": round(amount, 2),
        "risk_pct": round(risk_pct, 2),
        "equity": round(equity, 2),
        "confidence": round(confidence, 3),
        "win_rate": round(win_rate, 3),
        "text": (f"Dinamik boyut: ${amount:,.2f} (sermayenin %{risk_pct:.2f}) | "
                 f"equity=${equity:,.0f}, güven=%{confidence*100:.0f}, WR=%{win_rate*100:.0f}"),
    }
