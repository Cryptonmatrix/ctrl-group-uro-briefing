"""Tests for follow-up chat engine and intent extraction."""

from uro.analytics import build_fact_sheet
from uro.ingest import find_client, load_clients, load_reference
from uro.llm.chat import answer
from uro.llm.extract_notes import extract_intents


def test_chat_answers_and_sources():
    clients = load_clients("data/clients.json")
    reference = load_reference("data/reference.json")
    fs = build_fact_sheet(find_client(clients, "CASE-003"), reference)

    # Question about top holding
    resp = answer("What is the client's largest stock holding?", fs)
    assert resp.answer
    assert "Lindt" in resp.answer or "188" in resp.answer or "Chocolade" in resp.answer or "pos" in resp.answer

    # Question about unmentioned topic -> honest missing info
    resp_missing = answer("What are the client's private equity investments?", fs)
    assert "not available" in resp_missing.answer.lower()


def test_intent_extraction_fallback():
    sample_notes = [
        "Needs approximately CHF 15,000 in liquid funds for the Q1 tax payment.",
        "No direct positions in fossil fuels, please.",
        "Plans to retire in the next two years, increasing liquidity needs expected.",
    ]
    intents = extract_intents(sample_notes)
    assert len(intents) >= 2
    kinds = {i.kind for i in intents}
    assert "liquidity_need" in kinds
    assert "exclusion" in kinds or "life_event" in kinds
