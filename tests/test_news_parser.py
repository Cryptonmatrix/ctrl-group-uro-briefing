"""Tests for yfinance dual-format news parser."""

from uro.enrich.news import parse_news_item


def test_parse_modern_format():
    raw = {
        "content": {
            "title": "Swiss chip suppliers see strong quarterly demand",
            "summary": "Semiconductor companies in Zurich report margin expansion.",
            "pubDate": "2026-09-18T12:00:00Z",
            "provider": {"displayName": "Reuters"},
            "canonicalUrl": {"url": "https://reuters.com/news/article123"},
        }
    }
    parsed = parse_news_item(raw)
    assert parsed is not None
    assert parsed["title"] == "Swiss chip suppliers see strong quarterly demand"
    assert parsed["publisher"] == "Reuters"
    assert parsed["url"] == "https://reuters.com/news/article123"
    assert parsed["published_at"] is not None


def test_parse_legacy_format():
    raw = {
        "title": "Central Bank announces neutral policy trajectory",
        "publisher": "Bloomberg",
        "link": "https://bloomberg.com/news/456",
        "providerPublishTime": 1789732800,  # Valid unix timestamp
    }
    parsed = parse_news_item(raw)
    assert parsed is not None
    assert parsed["title"] == "Central Bank announces neutral policy trajectory"
    assert parsed["publisher"] == "Bloomberg"
    assert parsed["url"] == "https://bloomberg.com/news/456"
    assert parsed["published_at"] is not None


def test_parse_malformed_format():
    assert parse_news_item({}) is None
    assert parse_news_item("invalid string") is None  # type: ignore
