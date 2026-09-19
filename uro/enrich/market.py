"""OWNER: GIANLUCA — Orchestrierung von yfinance: Ticker-Auflösung, Kurshistorie und MarketSnapshot.

Ziele:
  - Budget: Gesamter Market-Schritt max. 8 s (ThreadPoolExecutor mit Timeout).
  - Resilienz: Disk-Cache je Klient (data/cache/market_<client_ref>.json) fängt Netzwerkausfälle auf der Bühne ab.
    Je Klient, weil ein gemeinsamer Cache die News und Kurse des zuletzt geladenen Klienten in ein fremdes
    Briefing tragen würde.
  - Niemals eine Exception nach oben werfen.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from datetime import date, datetime
from pathlib import Path

from uro.analytics.format import slug
from uro.analytics.market_comparison import proxy_tickers
from uro.config import get_settings
from uro.enrich.news import fetch_news
from uro.models import FactSheet, MarketSnapshot, PositionFact, PriceSeries

logger = logging.getLogger(__name__)

# In-memory memo for the process lifetime
_TICKER_MEMO: dict[int, str] = {}
_OVERRIDES_CACHE: dict[str, str] | None = None
_SECTOR_PROXIES_CACHE: dict[str, dict[str, str]] = {}


def _load_overrides() -> dict[str, str]:
    global _OVERRIDES_CACHE
    if _OVERRIDES_CACHE is None:
        p = Path("data/ticker_overrides.json")
        if p.exists():
            try:
                _OVERRIDES_CACHE = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                _OVERRIDES_CACHE = {}
        else:
            _OVERRIDES_CACHE = {}
    return _OVERRIDES_CACHE


def load_sector_proxies(path: str = "data/sector_proxies.json") -> dict[str, str]:
    global _SECTOR_PROXIES_CACHE
    if path not in _SECTOR_PROXIES_CACHE:
        p = Path(path)
        if p.exists():
            try:
                _SECTOR_PROXIES_CACHE[path] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                _SECTOR_PROXIES_CACHE[path] = {}
        else:
            _SECTOR_PROXIES_CACHE[path] = {}
    return _SECTOR_PROXIES_CACHE[path]


def resolve_single_ticker(pos: PositionFact) -> str | None:
    """Resolves an ISIN or name to a Yahoo ticker."""
    if pos.security_id in _TICKER_MEMO:
        return _TICKER_MEMO[pos.security_id]

    overrides = _load_overrides()
    if pos.isin and pos.isin in overrides:
        ticker = overrides[pos.isin]
        _TICKER_MEMO[pos.security_id] = ticker
        return ticker

    try:
        import yfinance as yf

        # Try ISIN first
        if pos.isin:
            search = yf.Search(pos.isin, max_results=3)
            if search.quotes:
                q = search.quotes[0]
                ticker = q.get("symbol")
                if ticker:
                    _TICKER_MEMO[pos.security_id] = ticker
                    return ticker

        # Try clean Name as fallback
        clean_name = pos.name.split("/")[0].split("-")[0].strip()
        search_name = yf.Search(clean_name, max_results=3)
        if search_name.quotes:
            q = search_name.quotes[0]
            ticker = q.get("symbol")
            if ticker:
                _TICKER_MEMO[pos.security_id] = ticker
                return ticker
    except Exception as exc:
        logger.debug("Failed ticker resolution for %s (%s): %s", pos.name, pos.isin, exc)

    return None


def resolve_tickers(positions: list[PositionFact], max_positions: int = 15) -> dict[int, str]:
    """Resolves tickers for top positions in parallel."""
    # Filter for equities/ETFs, exclude cash/bonds
    candidates = [p for p in positions if p.security_id and p.weight_pct > 0][:max_positions]

    resolved: dict[int, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_pos = {executor.submit(resolve_single_ticker, p): p for p in candidates}
        for future in concurrent.futures.as_completed(future_to_pos):
            pos = future_to_pos[future]
            try:
                ticker = future.result()
                if ticker:
                    resolved[pos.security_id] = ticker
            except Exception:
                pass

    return resolved


def fetch_prices(tickers: list[str], proxies: list[str] | None = None) -> dict[str, PriceSeries]:
    """Batch downloads 3-month price history for tickers and proxies."""
    all_tickers = list(dict.fromkeys(tickers + (proxies or [])))
    if not all_tickers:
        return {}

    try:
        import yfinance as yf

        # Download batch
        df = yf.download(
            all_tickers,
            period="3mo",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
            timeout=5.0,
        )
        if df is None or df.empty:
            return {}

        results: dict[str, PriceSeries] = {}

        if len(all_tickers) == 1:
            t = all_tickers[0]
            close_col = df["Close"] if "Close" in df else df
            dates = [
                d.date() if isinstance(d, datetime) else date.fromisoformat(str(d)[:10])
                for d in close_col.index
            ]
            closes = [float(v) for v in close_col.values if not str(v) == "nan"]
            results[t] = PriceSeries(ticker=t, dates=dates, closes=closes)
        else:
            for t in all_tickers:
                if t in df.columns.levels[0]:
                    sub_df = df[t]
                    if "Close" in sub_df:
                        series = sub_df["Close"].dropna()
                        dates = [
                            d.date() if isinstance(d, datetime) else date.fromisoformat(str(d)[:10])
                            for d in series.index
                        ]
                        closes = [float(v) for v in series.values]
                        results[t] = PriceSeries(ticker=t, dates=dates, closes=closes)

        return results
    except Exception as exc:
        logger.warning("Batch price download failed: %s", exc)
        return {}


def _cache_file(client_ref: str) -> Path:
    return Path("data/cache") / f"market_{slug(client_ref or 'unknown')}.json"


def _save_cache(snapshot: MarketSnapshot, client_ref: str) -> None:
    try:
        cache_file = _cache_file(client_ref)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    except Exception:
        logger.debug("Failed to write market snapshot disk cache")


def _load_cache(client_ref: str) -> MarketSnapshot | None:
    try:
        cache_file = _cache_file(client_ref)
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            snap = MarketSnapshot.model_validate(data)
            snap.source = "cache"
            snap.warnings.append("Using cached market data (offline mode)")
            return snap
    except Exception:
        logger.debug("Failed to read market snapshot disk cache")
    return None


def build_snapshot(fact_sheet: FactSheet, budget_s: float = 8.0) -> MarketSnapshot:
    """Orchestrates market resolution, prices, and news within a strict budget."""
    settings = get_settings()
    budget = budget_s or settings.market_budget_s

    # Flatten positions
    all_positions: list[PositionFact] = [pos for p in fact_sheet.portfolios for pos in p.positions]

    def _execute() -> MarketSnapshot:
        # 1. Resolve tickers
        ticker_map = resolve_tickers(all_positions, max_positions=settings.market_top_positions)
        tickers = list(ticker_map.values())

        # Proxies from proxy_tickers
        proxies = proxy_tickers(fact_sheet, ticker_map, load_sector_proxies())

        # 2. Fetch prices & news in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_prices = executor.submit(fetch_prices, tickers, proxies)
            fut_news = executor.submit(fetch_news, ticker_map)

            prices = fut_prices.result(timeout=settings.market_call_timeout_s)
            news = fut_news.result(timeout=settings.market_call_timeout_s)

        snap = MarketSnapshot(
            as_of=datetime.now(),
            source="live",
            tickers=ticker_map,
            prices=prices,
            news=news,
            warnings=[],
        )
        if settings.market_cache_enabled:
            _save_cache(snap, fact_sheet.client_ref)
        return snap

    # Kein `with`: dessen __exit__ ruft shutdown(wait=True) und wartet auf einen hängenden yfinance-Call —
    # dann gilt das Budget nicht. So kehren wir nach `budget` Sekunden zurück, der Thread läuft im Hintergrund aus.
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return executor.submit(_execute).result(timeout=budget)
    except Exception as exc:
        logger.warning("Market snapshot generation timed out or failed (%r). Checking cache.", exc)
        cached = _load_cache(fact_sheet.client_ref) if settings.market_cache_enabled else None
        if cached:
            return cached

        return MarketSnapshot(
            as_of=datetime.now(),
            source="unavailable",
            tickers={},
            prices={},
            news=[],
            warnings=["Market data unavailable"],
        )
    finally:
        executor.shutdown(wait=False)
