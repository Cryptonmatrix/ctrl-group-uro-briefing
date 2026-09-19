"""OWNER: GIANLUCA — Finanzmarkt-News zu den Top-Positionen und Branchen via yfinance.

Zwei Pflichten:
  - Beide yfinance-Newsformate (neu vs. alt) robust parsen.
  - Filter: nur letzte 14 Tage, dedupliziert, max. 6 Items als Findings news-1..6.
  - Offline-Fallback: Exceptions fangen, Warnung zurückgeben, nie abstürzen.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from uro.config import get_settings
from uro.models import Finding, FindingType, Severity

logger = logging.getLogger(__name__)


def parse_news_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Parses both modern and legacy yfinance news item formats into a clean dict."""
    if not isinstance(item, dict):
        return None

    # Modern format: item['content']
    content = item.get("content")
    if isinstance(content, dict):
        title = content.get("title")
        summary = content.get("summary") or ""
        provider = content.get("provider", {})
        publisher = provider.get("displayName") if isinstance(provider, dict) else ""
        canonical = content.get("canonicalUrl", {})
        url = canonical.get("url") if isinstance(canonical, dict) else ""
        pub_date_str = content.get("pubDate")
        pub_dt = None
        if pub_date_str:
            try:
                pub_dt = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except Exception:
                pub_dt = None
        return {
            "title": (title or "").strip(),
            "summary": summary.strip(),
            "publisher": (publisher or "Market News").strip(),
            "url": url or "",
            "published_at": pub_dt or datetime.now(UTC),
        }

    # Legacy format: flat dictionary
    title = item.get("title")
    if title:
        summary = item.get("summary") or ""
        publisher = item.get("publisher") or "Market News"
        url = item.get("link") or ""
        pub_ts = item.get("providerPublishTime")
        pub_dt = (
            datetime.fromtimestamp(pub_ts, tz=UTC) if isinstance(pub_ts, (int, float)) else datetime.now(UTC)
        )
        return {
            "title": str(title).strip(),
            "summary": str(summary).strip(),
            "publisher": str(publisher).strip(),
            "url": str(url).strip(),
            "published_at": pub_dt,
        }

    return None


def fetch_news(
    tickers: dict[int, str] | list[str],
    top_industries: list[str] | None = None,
) -> list[Finding]:
    """Fetches and normalizes news for resolved tickers and top industries."""
    settings = get_settings()
    ticker_list = list(tickers.values()) if isinstance(tickers, dict) else list(tickers)
    top_industries = top_industries or []

    if not ticker_list and not top_industries:
        return []

    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance is not installed. News fetch skipped.")
        return []

    raw_items: list[tuple[dict[str, Any], str]] = []  # (item, related_name)

    # 1. Fetch per-ticker news
    for t in ticker_list[:6]:
        try:
            ticker_obj = yf.Ticker(t)
            t_news = ticker_obj.news or []
            for item in t_news:
                raw_items.append((item, t))
        except Exception:
            logger.debug("Failed to fetch news for ticker %s", t)

    # 2. Parse, deduplicate, and filter by age
    now = datetime.now(UTC)
    max_age_days = settings.news_max_age_days
    seen_titles: set[str] = set()
    parsed_items = []

    for raw, tag in raw_items:
        parsed = parse_news_item(raw)
        if not parsed or not parsed["title"]:
            continue

        norm_title = parsed["title"].lower()
        if norm_title in seen_titles:
            continue
        seen_titles.add(norm_title)

        age_days = (now - parsed["published_at"]).total_seconds() / 86400
        if age_days > max_age_days:
            continue

        parsed["tag"] = tag
        parsed_items.append(parsed)

    # Sort newest first
    parsed_items.sort(key=lambda x: x["published_at"], reverse=True)

    findings: list[Finding] = []
    for idx, item in enumerate(parsed_items[: settings.news_max_items], 1):
        date_str = item["published_at"].strftime("%d %b")
        summary = item["summary"][:160] if item["summary"] else item["title"]
        findings.append(
            Finding(
                id=f"news-{idx}",
                type=FindingType.MARKET_EVENT,
                severity=Severity.INFO,
                title=f"[{item['publisher']}, {date_str}] {item['title']}",
                detail=f"{summary} (related: {item['tag']})",
                numbers={},
                source="news",
                score=0.40,
            )
        )

    return findings
