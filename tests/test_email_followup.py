"""Test suite for post-call follow-up email and internal sales guidance."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import uro.api as api
from uro.analytics import build_fact_sheet
from uro.ingest import find_client, load_clients, load_reference
from uro.llm.email_followup import validate_email_draft
from uro.llm.fallback import template_briefing, template_followup_email
from uro.models import (
    ClientFacingEmail,
    FollowUpEmailDraft,
    SalesOrientedNotes,
)


@pytest.fixture(scope="module")
def fact_sheet_case003():
    clients = load_clients("data/clients.json")
    reference = load_reference("data/reference.json")
    record = find_client(clients, "CASE-003")
    return build_fact_sheet(record, reference)


@pytest.fixture(scope="module")
def tc():
    with TestClient(api.app) as client:
        yield client


def test_template_followup_email_de(fact_sheet_case003):
    fs = fact_sheet_case003
    briefing = template_briefing(fs)
    draft = template_followup_email(fs, briefing, lang="de", display_name="Ron Burgundy")

    assert isinstance(draft, FollowUpEmailDraft)
    assert "Ron Burgundy" in draft.email.salutation
    assert "Zusammenfassung" in draft.email.subject
    assert len(draft.email.portfolio_recap) >= 1
    assert len(draft.email.agreed_next_steps) >= 1
    assert "Mit freundlichen Grüssen" in draft.email.closing
    assert len(draft.email.finding_ids) > 0

    # Sales Notes assertions
    assert len(draft.sales_notes.cross_sell_opportunities) >= 1
    assert len(draft.sales_notes.suitability_or_risk_actions) >= 1
    assert draft.sales_notes.next_contact_date_hint != ""
    assert "Ron Burgundy" in draft.sales_notes.crm_log_entry


def test_template_followup_email_en(fact_sheet_case003):
    fs = fact_sheet_case003
    briefing = template_briefing(fs)
    draft = template_followup_email(fs, briefing, lang="en", display_name="Ron Burgundy")

    assert isinstance(draft, FollowUpEmailDraft)
    assert "Dear Ron Burgundy" in draft.email.salutation
    assert "Summary" in draft.email.subject
    assert "Best regards" in draft.email.closing
    assert "business days" in draft.sales_notes.next_contact_date_hint


def test_validate_email_draft_flags_unsupported_numbers(fact_sheet_case003):
    fs = fact_sheet_case003
    email = ClientFacingEmail(
        subject="Test Subject",
        salutation="Dear Ron,",
        intro="Thank you.",
        portfolio_recap=["We achieved a fictional return of 99.85% which is not in the data."],
        agreed_next_steps=["Transfer CHF 8,888,888 immediately."],
        closing="Best regards",
        finding_ids=[],
    )
    draft = FollowUpEmailDraft(
        email=email,
        sales_notes=SalesOrientedNotes(crm_log_entry="Log"),
    )

    validated, issues = validate_email_draft(draft, fs)
    assert len(issues) >= 1
    kinds = [i.kind for i in issues]
    assert "unsupported_number" in kinds


def test_api_followup_email_lifecycle(tc):
    # 1. Reset state
    tc.post("/api/reset")

    # 2. Call followup-email before briefing -> Expect 409
    resp_before = tc.post("/api/clients/CASE-003/followup-email", json={"language": "de"})
    assert resp_before.status_code == 409
    assert "noch kein Briefing" in resp_before.json()["detail"]

    # 3. Generate briefing
    resp_briefing = tc.post("/api/clients/CASE-003/briefing")
    assert resp_briefing.status_code == 200

    # 4. Call followup-email after briefing -> Expect 200
    resp_after = tc.post("/api/clients/CASE-003/followup-email", json={"language": "de"})
    assert resp_after.status_code == 200
    data = resp_after.json()

    assert data["client_ref"] == "CASE-003"
    assert "email" in data
    assert "sales_notes" in data
    assert data["email"]["subject"] != ""
    assert len(data["email"]["agreed_next_steps"]) >= 1
    assert len(data["sales_notes"]["cross_sell_opportunities"]) >= 1
    assert data["sales_notes"]["crm_log_entry"] != ""
