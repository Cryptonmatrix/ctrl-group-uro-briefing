"""OWNER: GIANLUCA — Anthropic API Client Factory und structured logging."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic

from uro.config import get_settings

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """Raised when the Anthropic API key is missing or the service cannot be reached."""


class LLMInvalid(Exception):
    """Raised when the LLM response is malformed or structurally invalid."""


def get_client() -> anthropic.Anthropic:
    """Returns a configured Anthropic client, or raises LLMUnavailable if no key is configured."""
    settings = get_settings()
    api_key = settings.anthropic_api_key
    if not api_key or not api_key.strip():
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set in environment or .env file.")

    return anthropic.Anthropic(
        api_key=api_key.strip(),
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )


def log_llm(kind: str, client_ref: str, request: dict[str, Any], response: Any) -> None:
    """Logs LLM requests and responses for debugging and audit purposes."""
    settings = get_settings()
    log_dir = Path(settings.log_dir) / "llm"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        safe_ref = client_ref.replace("/", "_").replace("\\", "_")
        filename = log_dir / f"{ts}_{safe_ref}_{kind}.json"

        # Serialize response if pydantic or dict
        if hasattr(response, "model_dump"):
            resp_data = response.model_dump()
        elif hasattr(response, "dict"):
            resp_data = response.dict()
        elif isinstance(response, (dict, list, str, int, float, bool)) or response is None:
            resp_data = response
        else:
            resp_data = str(response)

        payload = {
            "timestamp": datetime.now().isoformat(),
            "kind": kind,
            "client_ref": client_ref,
            "request": request,
            "response": resp_data,
        }
        filename.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except Exception:
        logger.exception("Failed to write LLM audit log for %s", client_ref)
