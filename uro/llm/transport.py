"""HTTP-Transport für die Anthropic-API über die Standardbibliothek.

WARUM NICHT DAS SDK: In der Nacht vom 19.09. hing das anthropic-SDK auf diesem
Rechner reproduzierbar — auch mit `timeout=60, max_retries=0` kam nach über
280 Sekunden keine Rückmeldung. Derselbe Request per curl: 19,5 s. Per
urllib aus der Standardbibliothek: 19,1 s. Die Ursache liegt im httpx2-Transport
des SDK, dessen Timeout in dieser Umgebung nicht greift.

Ein Timeout, der nicht auslöst, ist auf der Bühne schlimmer als jeder Fehler:
Das UI friert ein und niemand weiss, warum. Deshalb dieser Weg — schmal,
ohne Abhängigkeit, und mit einem Timeout, der nachweislich auslöst.

Zu prüfen nach dem Hackathon, ob das SDK auf anderen Rechnern sauber läuft.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class LLMError(RuntimeError):
    """Basisklasse. api.py und demo.py fangen die Unterklassen einzeln ab."""


class LLMTimeout(LLMError):
    pass


class LLMAuthError(LLMError):
    pass


class LLMRateLimit(LLMError):
    pass


class LLMServerError(LLMError):
    pass


class LLMBadRequest(LLMError):
    pass


def post_messages(payload: dict, timeout: float = 60.0, retries: int = 1) -> dict:
    """Ein Aufruf an /v1/messages. Wirft immer eine LLMError-Unterklasse, nie stillschweigend."""
    # Umgebung zuerst, sonst .env über die Settings — dieselbe Quelle wie llm/client.get_client,
    # damit ein Schlüssel, der nur in .env steht, nicht still ins Template-Fallback führt.
    from uro.config import get_settings

    key = (os.environ.get("ANTHROPIC_API_KEY") or get_settings().anthropic_api_key or "").strip()
    if not key:
        raise LLMAuthError("ANTHROPIC_API_KEY ist nicht gesetzt.")

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
    )

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:400]
            if exc.code == 401:
                raise LLMAuthError(
                    "Der API-Schlüssel wird abgelehnt. Ist er einem Workspace zugeordnet?"
                ) from None
            if exc.code == 400:
                raise LLMBadRequest(f"Die API hat den Request abgelehnt: {body}") from None
            if exc.code == 429:
                last = LLMRateLimit("Rate Limit erreicht.")
            elif exc.code >= 500:
                last = LLMServerError(f"Serverfehler {exc.code}.")
            else:
                raise LLMError(f"HTTP {exc.code}: {body}") from None
        except TimeoutError:
            last = LLMTimeout(f"Keine Antwort innerhalb von {timeout:.0f} Sekunden.")
        except urllib.error.URLError as exc:
            last = LLMError(f"Keine Verbindung zur API: {exc.reason}")

        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))

    raise last or LLMError("Unbekannter Fehler beim API-Aufruf.")
