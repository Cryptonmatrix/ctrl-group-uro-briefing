"""Follow-up-Chat: Claude über den stdlib-Transport (nicht das SDK), nur echte Quellen, angereichertes Fact Sheet."""

from __future__ import annotations

import uro.llm.chat as chat_mod
from uro.config import get_settings
from uro.llm.chat import answer


def test_chat_uses_transport_and_keeps_only_known_sources(fact_sheets, monkeypatch):
    fs = fact_sheets["CASE-A01"]
    sent = {}

    def fake_post(payload, timeout, retries):
        sent.update(payload)
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Volatility is above the limit [risk-breach-CASE-A01-01] [made-up-id].",
                }
            ]
        }

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    monkeypatch.setattr(chat_mod, "post_messages", fake_post)

    resp = answer(
        "Is the portfolio too risky?",
        fs,
        history=[{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}],
    )

    assert resp.sources == ["risk-breach-CASE-A01-01"]  # erfundene ID fällt raus
    assert sent["messages"][-1] == {"role": "user", "content": "Is the portfolio too risky?"}
    assert "risk-breach-CASE-A01-01" in sent["messages"][0]["content"]  # Kontext enthält die Findings


def test_chat_falls_back_to_rules_when_llm_fails(fact_sheets, monkeypatch):
    def failing_post(payload, timeout, retries):
        raise TimeoutError("no answer")

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    monkeypatch.setattr(get_settings(), "google_api_key", None)
    monkeypatch.setattr(chat_mod, "post_messages", failing_post)

    resp = answer("What is the largest holding?", fact_sheets["CASE-A01"])

    assert "largest holding" in resp.answer and resp.sources == ["pos-101"]
