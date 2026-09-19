"""OWNER: GIANLUCA — Tier 2 LLM Failover via Google Gemini.

Nutzt Google Gemini (z.B. gemini-3.5-flash-lite oder gemini-3.5) als sekundären
LLM-Provider, wenn der primäre Claude-Aufruf fehlschlägt oder kein Anthropic-Key
vorhanden ist.

Verwendet natives httpx mit REST-Aufruf und strukturiertem JSON-Schema.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from typing import Any

import httpx

from uro.config import get_settings
from uro.llm.client import LLMInvalid, LLMUnavailable, log_llm
from uro.llm.prompts import SYSTEM_PROMPT, render_fact_sheet
from uro.models import Briefing, FactSheet

logger = logging.getLogger(__name__)


def _clean_for_gemini(node: Any, defs: dict[str, Any]) -> Any:
    """Recursively inlines $ref and removes fields unsupported by Gemini response_schema."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref_name = node["$ref"].split("/")[-1]
            target = copy.deepcopy(defs.get(ref_name, {}))
            return _clean_for_gemini(target, defs)

        cleaned: dict[str, Any] = {}
        for k, v in node.items():
            # Gemini does not accept $defs, extra, default, or additionalProperties
            if k in ("$defs", "extra", "default", "additionalProperties"):
                continue
            # Only strip schema metadata 'title' (which is a string), not a property named 'title'
            if k == "title" and isinstance(v, str):
                continue
            cleaned[k] = _clean_for_gemini(v, defs)
        return cleaned
    elif isinstance(node, list):
        return [_clean_for_gemini(item, defs) for item in node]
    return node


def get_gemini_briefing_schema() -> dict[str, Any]:
    """Generates an OpenAPI 3.0 schema strictly compatible with Google Gemini."""
    raw = Briefing.model_json_schema()
    defs = raw.get("$defs", {})
    schema = _clean_for_gemini(raw, defs)
    schema.pop("$defs", None)
    return schema


def get_gemini_api_key() -> str:
    """Resolves the Gemini API key from settings or environment variables."""
    settings = get_settings()
    key = (
        settings.gemini_api_key
        or settings.google_api_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if not key or not key.strip():
        raise LLMUnavailable("Neither GEMINI_API_KEY nor GOOGLE_API_KEY is configured.")
    return key.strip()


def generate_briefing_gemini(fact_sheet: FactSheet) -> Briefing:
    """Generates a structured Briefing using Google Gemini with native JSON schema."""
    api_key = get_gemini_api_key()
    settings = get_settings()

    user_text = render_fact_sheet(fact_sheet)
    model = settings.gemini_model

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_text}]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": get_gemini_briefing_schema(),
            "temperature": 0.2,
        },
    }

    try:
        with httpx.Client(timeout=settings.gemini_timeout_s) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMInvalid(f"Gemini returned no candidates: {data}")

        first_part = candidates[0].get("content", {}).get("parts", [{}])[0]
        text = first_part.get("text")
        if not text:
            raise LLMInvalid("Gemini returned empty text in candidate content.")

        parsed_json = json.loads(text)
        briefing = Briefing.model_validate(parsed_json)

        log_llm("briefing_gemini", fact_sheet.client_ref, {"model": model}, briefing)
        return briefing

    except httpx.HTTPStatusError as exc:
        logger.warning("Gemini HTTP error (%s): %s", exc.response.status_code, exc.response.text[:300])
        raise LLMUnavailable(f"Gemini API returned status {exc.response.status_code}: {exc.response.text[:100]}") from exc
    except Exception as exc:
        logger.warning("Gemini briefing generation failed: %s", exc)
        raise LLMInvalid(f"Gemini generation error: {exc}") from exc


def ask_chat_gemini(context_str: str, question: str, history: list[dict] | None = None) -> str:
    """Answers a follow-up question via Gemini using strict grounding prompt."""
    api_key = get_gemini_api_key()
    settings = get_settings()
    model = settings.gemini_model

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    from uro.llm.prompts import CHAT_SYSTEM_PROMPT

    contents = [
        {
            "role": "user",
            "parts": [{"text": f"CLIENT DATA CONTEXT:\n{context_str}\n\nPlease answer the question below strictly based on this data."}],
        },
        {
            "role": "model",
            "parts": [{"text": "I have reviewed the client context and will answer based strictly on the facts provided, citing finding IDs or position IDs."}],
        },
    ]
    if history:
        for h in history[-4:]:
            role = "model" if h.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})

    contents.append({
        "role": "user",
        "parts": [{"text": question}],
    })

    payload = {
        "system_instruction": {
            "parts": [{"text": CHAT_SYSTEM_PROMPT}],
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 800,
        },
    }

    try:
        with httpx.Client(timeout=settings.gemini_timeout_s) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMInvalid("Gemini chat returned no candidates")

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return text
    except Exception as exc:
        logger.warning("Gemini chat failed: %s", exc)
        raise LLMUnavailable(f"Gemini chat unavailable: {exc}") from exc

