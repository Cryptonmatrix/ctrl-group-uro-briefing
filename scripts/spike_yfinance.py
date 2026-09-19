"""Spike script for yfinance ticker resolution, batch download, and news parsing."""

import time

from uro.enrich.market import fetch_prices, resolve_tickers
from uro.enrich.news import fetch_news
from uro.models import PositionFact

TEST_POSITIONS = [
    PositionFact(
        security_id=9108,
        name="Chocoladefabriken Lindt & Sprüngli",
        isin="CH0012221716",
        currency="CHF",
        amount_chf=100000.0,
        weight_pct=73.4,
    ),
    PositionFact(
        security_id=8921,
        name="Sensirion Holding AG",
        isin="CH0406705126",
        currency="CHF",
        amount_chf=30000.0,
        weight_pct=24.0,
    ),
    PositionFact(
        security_id=1001,
        name="Nestlé S.A.",
        isin="CH0038863350",
        currency="CHF",
        amount_chf=50000.0,
        weight_pct=15.0,
    ),
    PositionFact(
        security_id=1002,
        name="ASML Holding NV",
        isin="NL0010273215",
        currency="EUR",
        amount_chf=20000.0,
        weight_pct=10.0,
    ),
]


def run_spike():
    print("=== 1. Testing Ticker Resolution ===")
    t0 = time.perf_counter()
    resolved = resolve_tickers(TEST_POSITIONS)
    t_res = time.perf_counter() - t0
    print(f"Resolved {len(resolved)} / {len(TEST_POSITIONS)} in {t_res:.2f}s:")
    for sid, ticker in resolved.items():
        print(f"  Security {sid} -> {ticker}")

    print("\n=== 2. Testing Batch Price Download ===")
    tickers = list(resolved.values())
    proxies = ["^SSMI", "SOXX"]
    t0 = time.perf_counter()
    prices = fetch_prices(tickers, proxies)
    t_prices = time.perf_counter() - t0
    print(f"Downloaded prices for {len(prices)} tickers in {t_prices:.2f}s:")
    for t, ps in prices.items():
        ret = ps.return_pct()
        ret_str = f"{ret:+.2f}%" if ret is not None else "N/A"
        print(f"  {t:10}: {len(ps.closes)} days, 3M return: {ret_str}")

    print("\n=== 3. Testing News Retrieval ===")
    t0 = time.perf_counter()
    news = fetch_news(resolved)
    t_news = time.perf_counter() - t0
    print(f"Fetched {len(news)} news findings in {t_news:.2f}s:")
    for n in news:
        print(f"  [{n.id}] {n.title[:70]}...")

    print(f"\nTotal elapsed: {t_res + t_prices + t_news:.2f}s (Budget: 8.0s)")


if __name__ == "__main__":
    run_spike()
