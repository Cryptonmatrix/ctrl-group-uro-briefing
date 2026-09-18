"""Tests for Tier 2 Google Gemini failover."""

from unittest.mock import MagicMock, patch

from uro.llm.briefing import generate_briefing
from uro.llm.gemini import generate_briefing_gemini
from uro.models import (
    Briefing,
    FactSheet,
    Finding,
    FindingType,
    NextBestAction,
    Section,
    Severity,
    Statement,
    StatementType,
)


def _sample_briefing_dict():
    b = Briefing(
        headline="Gemini generated review headline",
        sections=[
            Section(
                title="Recent Portfolio Development",
                statements=[
                    Statement(
                        text="Portfolio performance reported.",
                        type=StatementType.FACT,
                        finding_ids=["perf-1"],
                    )
                ],
            ),
            Section(title="Portfolio Health Check", statements=[]),
            Section(title="Portfolio Outlook & Next Best Actions", statements=[]),
        ],
        next_best_actions=[
            NextBestAction(
                action="Rebalance allocation",
                rationale="Bring back to targets",
                finding_ids=["perf-1"],
            )
        ],
    )
    return b.model_dump()


def _make_fs():
    return FactSheet(
        client_ref="GEMINI-001",
        findings=[
            Finding(
                id="perf-1",
                type=FindingType.PERFORMANCE,
                severity=Severity.INFO,
                title="Portfolio return +5.0%",
                detail="Positive quarter.",
                numbers={"perf_pct": 5.0},
            )
        ],
    )


def test_generate_briefing_gemini_mocked():
    fs = _make_fs()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": Briefing.model_validate(_sample_briefing_dict()).model_dump_json()}]
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp), patch(
        "uro.llm.gemini.get_gemini_api_key", return_value="fake-gemini-key"
    ):
        briefing = generate_briefing_gemini(fs)
        assert isinstance(briefing, Briefing)
        assert briefing.headline == "Gemini generated review headline"
        assert len(briefing.sections) == 3


def test_briefing_failover_to_gemini_when_anthropic_missing():
    fs = _make_fs()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": Briefing.model_validate(_sample_briefing_dict()).model_dump_json()}]
                }
            }
        ]
    }

    # Simulate Anthropic key missing, but Gemini available
    with patch("httpx.Client.post", return_value=mock_resp), patch(
        "uro.llm.gemini.get_gemini_api_key", return_value="fake-gemini-key"
    ), patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
        briefing, mode = generate_briefing(fs)
        assert mode == "ai_gemini"
        assert isinstance(briefing, Briefing)
        assert briefing.headline == "Gemini generated review headline"


def test_briefing_full_failover_to_fallback():
    fs = _make_fs()
    # When both Anthropic and Gemini fail/are unconfigured
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
        briefing, mode = generate_briefing(fs)
        assert mode == "fallback"
        assert isinstance(briefing, Briefing)
        assert len(briefing.sections) == 3
