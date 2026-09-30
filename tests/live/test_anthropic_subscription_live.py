"""Account-gated live smoke for Anthropic subscription OAuth.

The normal suite skips this module. Verification starts a fresh Odysseus
backend with an isolated data directory, provisions that temporary database
from an already-authenticated local account, and opts in with
``ODYSSEUS_ANTHROPIC_LIVE=1``.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("ODYSSEUS_ANTHROPIC_LIVE") != "1",
    reason="requires an authenticated local Anthropic subscription account",
)


def test_live_subscription_stream_through_running_odysseus():
    base_url = os.environ["ODYSSEUS_LIVE_BASE_URL"].rstrip("/")
    requested_model = os.getenv("ODYSSEUS_ANTHROPIC_LIVE_MODEL", "").strip()

    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        assert health.json()["status"] == "healthy"

        status = client.get("/api/anthropic-subscription/status")
        status.raise_for_status()
        connection = status.json()
        assert connection["connected"] is True
        endpoint = connection["endpoint"]
        assert endpoint["id"]

        refreshed = client.get(
            f"/api/model-endpoints/{endpoint['id']}/models",
            params={"refresh": "true"},
        )
        refreshed.raise_for_status()
        assert (
            refreshed.headers.get("X-Model-Refresh-Status")
            == "refreshed"
        )
        advertised_models = [
            item["id"] for item in refreshed.json()
        ]
        assert advertised_models

        status = client.get("/api/anthropic-subscription/status")
        status.raise_for_status()
        endpoint = status.json()["endpoint"]
        assert endpoint["models"] == advertised_models
        if requested_model:
            assert requested_model in advertised_models
            models_to_test = [requested_model]
        else:
            models_to_test = advertised_models

        for model in models_to_test:
            created = client.post(
                "/api/session",
                data={
                    "name": (
                        "Anthropic subscription live verification "
                        f"({model})"
                    ),
                    "endpoint_id": endpoint["id"],
                    "model": model,
                    "skip_validation": "true",
                },
            )
            created.raise_for_status()
            session_id = created.json()["id"]

            deltas: list[str] = []
            errors: list[dict] = []
            try:
                with client.stream(
                    "POST",
                    "/api/chat_stream",
                    data={
                        "session": session_id,
                        "message": (
                            "Briefly confirm that you are available."
                        ),
                        "mode": "chat",
                        "use_web": "false",
                        "use_research": "false",
                    },
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        if raw == "[DONE]":
                            break
                        event = json.loads(raw)
                        if event.get("error"):
                            errors.append(event)
                        if event.get("delta") and not event.get("thinking"):
                            deltas.append(str(event["delta"]))
            finally:
                client.post(f"/api/session/{session_id}/delete")

            assert not errors, (
                f"live stream for {model} returned a safe error event: "
                f"{errors}"
            )
            text = "".join(deltas).strip()
            assert text, (
                f"live Anthropic subscription stream for {model} "
                "returned no text"
            )
