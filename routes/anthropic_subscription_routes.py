"""Owner-scoped Anthropic subscription OAuth setup routes."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.database import (
    ModelEndpoint,
    ProviderAuthSession,
    SessionLocal,
    utcnow_naive,
)
from src import anthropic_subscription
from src.auth_helpers import get_current_user


class AnthropicOAuthCompleteRequest(BaseModel):
    attempt_id: str
    callback: str


def _owner(request: Request) -> Optional[str]:
    return get_current_user(request) or None


def _invalidate_models_cache() -> None:
    try:
        from routes.model_routes import _invalidate_models_cache as invalidate

        invalidate()
    except Exception:
        pass


def _route_http_exception(exc: Exception) -> HTTPException:
    mapped = anthropic_subscription.to_http_exception(exc)
    if mapped.status_code == 429:
        return mapped
    if mapped.status_code == 401 and "Reconnect" not in str(mapped.detail):
        return HTTPException(401, f"{mapped.detail} Reconnect the provider.")
    return mapped


def _provision_endpoint(tokens: Dict[str, Any], owner: Optional[str]) -> Dict[str, Any]:
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not access_token or not refresh_token:
        raise anthropic_subscription.AnthropicSubscriptionReauthRequired(
            "Anthropic token response was missing access or refresh credentials."
        )

    base = anthropic_subscription.DEFAULT_ANTHROPIC_SUBSCRIPTION_BASE_URL
    try:
        discovered_models = anthropic_subscription.fetch_available_models(
            access_token
        )
    except Exception:
        discovered_models = []
    db = SessionLocal()
    try:
        auth = (
            db.query(ProviderAuthSession)
            .filter(
                ProviderAuthSession.provider
                == anthropic_subscription.ANTHROPIC_SUBSCRIPTION_PROVIDER,
                ProviderAuthSession.owner == owner,
            )
            .first()
        )
        if auth is None:
            auth = ProviderAuthSession(
                id=str(uuid.uuid4())[:8],
                provider=anthropic_subscription.ANTHROPIC_SUBSCRIPTION_PROVIDER,
                owner=owner,
                label="Anthropic Subscription (experimental)",
                base_url=base,
                auth_mode=(
                    anthropic_subscription.ANTHROPIC_SUBSCRIPTION_AUTH_MODE
                ),
            )
            db.add(auth)
            db.flush()

        # Reconnect updates the same owner-scoped encrypted auth row.
        auth.base_url = base
        auth.access_token = access_token
        auth.refresh_token = refresh_token
        auth.expires_at = anthropic_subscription.token_expiry(
            tokens.get("expires_in"), now=utcnow_naive()
        )
        auth.last_refresh = utcnow_naive()
        auth.auth_mode = anthropic_subscription.ANTHROPIC_SUBSCRIPTION_AUTH_MODE

        endpoint = (
            db.query(ModelEndpoint)
            .filter(
                ModelEndpoint.provider_auth_id == auth.id,
                ModelEndpoint.owner == owner,
            )
            .first()
        )
        if endpoint is None:
            endpoint = ModelEndpoint(
                id=str(uuid.uuid4())[:8],
                name="Anthropic Subscription (experimental)",
                base_url=base,
                owner=owner,
            )
            db.add(endpoint)
        cached_models: list[str] = []
        try:
            loaded = json.loads(endpoint.cached_models or "[]")
            if isinstance(loaded, list):
                cached_models = [
                    str(model)
                    for model in loaded
                    if isinstance(model, str) and model
                ]
        except (TypeError, ValueError):
            pass
        models = (
            discovered_models
            or cached_models
            or list(
                anthropic_subscription.CURATED_ANTHROPIC_SUBSCRIPTION_MODELS
            )
        )
        endpoint.name = "Anthropic Subscription (experimental)"
        endpoint.base_url = base
        endpoint.api_key = None
        endpoint.provider_auth_id = auth.id
        endpoint.is_enabled = True
        endpoint.model_type = "llm"
        endpoint.endpoint_kind = "api"
        endpoint.model_refresh_mode = "manual"
        endpoint.supports_tools = True
        endpoint.cached_models = json.dumps(models)
        if discovered_models:
            available = set(models)
            for attr in ("pinned_models", "hidden_models"):
                try:
                    current = json.loads(getattr(endpoint, attr, None) or "[]")
                except (TypeError, ValueError):
                    current = []
                retained = [
                    model
                    for model in current
                    if isinstance(model, str) and model in available
                ]
                setattr(
                    endpoint,
                    attr,
                    json.dumps(retained) if retained else None,
                )
        db.commit()
        result = {
            "id": endpoint.id,
            "name": endpoint.name,
            "base_url": endpoint.base_url,
            "models": models,
            "experimental": True,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    _invalidate_models_cache()
    return result


def _status(owner: Optional[str]) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        auth = (
            db.query(ProviderAuthSession)
            .filter(
                ProviderAuthSession.provider
                == anthropic_subscription.ANTHROPIC_SUBSCRIPTION_PROVIDER,
                ProviderAuthSession.owner == owner,
            )
            .first()
        )
        if auth is None:
            return {"connected": False, "experimental": True}
        endpoint = (
            db.query(ModelEndpoint)
            .filter(
                ModelEndpoint.provider_auth_id == auth.id,
                ModelEndpoint.owner == owner,
            )
            .first()
        )
        models: list[str] = []
        if endpoint is not None:
            try:
                loaded = json.loads(endpoint.cached_models or "[]")
                if isinstance(loaded, list):
                    models = [str(model) for model in loaded]
            except (TypeError, ValueError):
                pass
        return {
            "connected": bool(endpoint and endpoint.is_enabled),
            "experimental": True,
            "endpoint": (
                {
                    "id": endpoint.id,
                    "name": endpoint.name,
                    "models": models,
                }
                if endpoint is not None
                else None
            ),
            "expires_at": (
                auth.expires_at.isoformat() if auth.expires_at is not None else None
            ),
        }
    finally:
        db.close()


def _disconnect(owner: Optional[str]) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        auth_rows = (
            db.query(ProviderAuthSession)
            .filter(
                ProviderAuthSession.provider
                == anthropic_subscription.ANTHROPIC_SUBSCRIPTION_PROVIDER,
                ProviderAuthSession.owner == owner,
            )
            .all()
        )
        auth_ids = [row.id for row in auth_rows]
        endpoint_rows = []
        if auth_ids:
            endpoint_rows = (
                db.query(ModelEndpoint)
                .filter(
                    ModelEndpoint.owner == owner,
                    ModelEndpoint.provider_auth_id.in_(auth_ids),
                )
                .all()
            )
        endpoint_ids = [row.id for row in endpoint_rows]
        for endpoint in endpoint_rows:
            db.delete(endpoint)
        for auth in auth_rows:
            db.delete(auth)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    _invalidate_models_cache()
    return {
        "disconnected": bool(auth_ids or endpoint_ids),
        "removed_endpoint_ids": endpoint_ids,
    }


def setup_anthropic_subscription_routes() -> APIRouter:
    router = APIRouter(
        prefix="/api/anthropic-subscription",
        tags=["anthropic-subscription"],
    )

    @router.post("/oauth/start")
    def start(request: Request):
        return anthropic_subscription.start_authorization(_owner(request))

    @router.post("/oauth/complete")
    def complete(body: AnthropicOAuthCompleteRequest, request: Request):
        owner = _owner(request)
        try:
            tokens = anthropic_subscription.complete_authorization(
                owner,
                body.attempt_id,
                body.callback,
            )
            endpoint = _provision_endpoint(tokens, owner)
        except Exception as exc:
            raise _route_http_exception(exc)
        return {"status": "authorized", "endpoint": endpoint}

    @router.get("/status")
    def status(request: Request):
        return _status(_owner(request))

    @router.delete("/connection")
    def disconnect(request: Request):
        return _disconnect(_owner(request))

    return router
