"""The check on an operator's override, the one line that reaches every viewer without passing through a model.

AI lines and their versions already pass the models' content filter and the variant checks; an override is typed
by whoever holds the console, which is open during judging. So before it is recorded or aired it must pass the
banned-topic rule the variants follow, and Azure AI Content Safety on the Foundry account (Entra ID, no key).

Fails closed in Azure: if the check can't run, the override is refused and nothing airs. Errors are one plain
sentence, which the console shows as is; "can't be checked" is a 424, not a 503, which the console would read as
"the API isn't answering". Locally (no endpoint, not in Container Apps) only the banned-topic rule runs, so
development and tests need no Azure.
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import HTTPException

from .variant_checks import mentions_banned_topic

logger = logging.getLogger(__name__)

API_VERSION = "2024-09-01"
SCOPE = "https://cognitiveservices.azure.com/.default"
TIMEOUT_S = 3.0
# Refused from this severity up (0, 2, 4, 6). Violence starts at Medium, so match language ("smashed it",
# "a thunderbolt") passes; the others refuse from Low.
BLOCK_AT = {"Hate": 2, "Sexual": 2, "SelfHarm": 2, "Violence": 4}

_credential = None


async def _token() -> str:
    global _credential
    if _credential is None:
        from azure.identity.aio import DefaultAzureCredential

        _credential = DefaultAzureCredential()
    return (await _credential.get_token(SCOPE)).token


async def _analyze(endpoint: str, text: str) -> dict[str, int]:
    import aiohttp

    url = f"{endpoint.rstrip('/')}/contentsafety/text:analyze?api-version={API_VERSION}"
    body = {"text": text, "categories": list(BLOCK_AT), "outputType": "FourSeverityLevels"}
    headers = {"Authorization": f"Bearer {await _token()}"}
    async with aiohttp.ClientSession() as session, session.post(url, json=body, headers=headers) as r:
        r.raise_for_status()
        result = await r.json()
    severities = {c["category"]: c["severity"] for c in result["categoriesAnalysis"]}
    if set(severities) != set(BLOCK_AT):
        raise ValueError(f"incomplete analysis: {sorted(severities)}")
    return severities


async def check_override(text: str) -> None:
    """Returns only when the line may air. 422 if it is refused, 424 if it could not be checked."""
    if mentions_banned_topic(text):
        raise HTTPException(422, "the override wasn't aired: refereeing, betting and injuries are kept off air")
    endpoint = os.environ.get("AZURE_CONTENT_SAFETY_ENDPOINT", "")
    if not endpoint:
        if os.environ.get("CONTAINER_APP_NAME"):  # set by Container Apps itself: never skip the check in Azure
            raise HTTPException(424, "the override check isn't configured, so the line was not aired")
        return
    try:
        severities = await asyncio.wait_for(_analyze(endpoint, text), timeout=TIMEOUT_S)
    except Exception as ex:  # noqa: BLE001 - a timeout, auth or HTTP error: fail closed
        logger.warning("override check failed, line refused: %s", type(ex).__name__)
        raise HTTPException(424, "the override check is unavailable, so the line was not aired") from ex
    flagged = sorted(c for c, severity in severities.items() if severity >= BLOCK_AT[c])
    if flagged:
        raise HTTPException(422, "the override wasn't aired: Content Safety flagged it ("
                                 + ", ".join(c.lower() for c in flagged) + ")")
