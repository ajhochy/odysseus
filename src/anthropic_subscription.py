"""Anthropic subscription OAuth helpers.

This compatibility provider is deliberately isolated from Anthropic API-key
endpoints. OAuth tokens stay in ``ProviderAuthSession`` and are resolved into
request-local bearer headers only when a request is dispatched.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from fastapi import HTTPException


ANTHROPIC_SUBSCRIPTION_PROVIDER = "anthropic-subscription"
ANTHROPIC_SUBSCRIPTION_AUTH_MODE = "anthropic-subscription"
DEFAULT_ANTHROPIC_SUBSCRIPTION_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_OAUTH_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
ANTHROPIC_OAUTH_TOKEN_URL = "https://claude.ai/v1/oauth/token"
ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_OAUTH_REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
ANTHROPIC_OAUTH_SCOPES = "org:create_api_key user:profile user:inference"
ANTHROPIC_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 60
ANTHROPIC_PENDING_AUTHORIZATION_SECONDS = 600
ANTHROPIC_VERSION = "2023-06-01"
CLAUDE_CODE_SYSTEM_IDENTITY = "You are Claude Code, Anthropic's official CLI for Claude."
OAUTH_BETAS = (
    "interleaved-thinking-2025-05-14",
    "fine-grained-tool-streaming-2025-05-14",
    "claude-code-20250219",
    "oauth-2025-04-20",
)
OAUTH_BETA = ",".join(OAUTH_BETAS)
# Never opt a subscription into long-context billing implicitly.
assert all("1m" not in beta.lower() for beta in OAUTH_BETAS)

CURATED_ANTHROPIC_SUBSCRIPTION_MODELS = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-haiku-4-5-20251001",
)

_AUTH_REFRESH_LOCKS: dict[str, threading.Lock] = {}
_AUTH_REFRESH_LOCKS_GUARD = threading.Lock()


def _database_handles():
    from core.database import ProviderAuthSession, SessionLocal, utcnow_naive

    return ProviderAuthSession, SessionLocal, utcnow_naive


class AnthropicSubscriptionError(RuntimeError):
    """Base error for safe, user-facing subscription failures."""


class AnthropicSubscriptionFlowError(AnthropicSubscriptionError):
    """The pasted authorization flow is invalid, expired, or already used."""


class AnthropicSubscriptionReauthRequired(AnthropicSubscriptionError):
    """Stored credentials are missing or rejected. Reconnect is required."""


class AnthropicSubscriptionRateLimited(AnthropicSubscriptionError):
    """Plan quota or upstream rate limiting; reconnecting will not fix it."""


class AnthropicSubscriptionAuthNotFound(AnthropicSubscriptionReauthRequired):
    """No owner-scoped auth session exists."""


class AnthropicSubscriptionDenied(AnthropicSubscriptionFlowError):
    """The user denied the authorization request."""


@dataclass
class PendingAuthorization:
    """One owner-bound, independent and single-use PKCE attempt."""

    attempt_id: str
    owner: Optional[str]
    state: str
    code_verifier: str
    expires_at: float


class PendingAuthorizationStore:
    """Thread-safe in-memory store for short-lived pasted-code flows."""

    def __init__(self) -> None:
        self._items: dict[str, PendingAuthorization] = {}
        self._lock = threading.Lock()

    def create(self, owner: Optional[str], now: Optional[float] = None) -> PendingAuthorization:
        current = time.time() if now is None else float(now)
        pending = PendingAuthorization(
            attempt_id=secrets.token_urlsafe(24),
            owner=owner,
            state=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(48),
            expires_at=current + ANTHROPIC_PENDING_AUTHORIZATION_SECONDS,
        )
        with self._lock:
            self._items[pending.attempt_id] = pending
        return pending

    def consume_validated(
        self,
        attempt_id: str,
        owner: Optional[str],
        received_state: str,
        now: Optional[float] = None,
    ) -> PendingAuthorization:
        current = time.time() if now is None else float(now)
        with self._lock:
            pending = self._items.get(attempt_id)
            if pending is None:
                raise AnthropicSubscriptionFlowError(
                    "This authorization attempt is missing or was already used. Start again."
                )
            if pending.owner != owner:
                raise AnthropicSubscriptionFlowError(
                    "This authorization attempt belongs to another user. Start again."
                )
            if pending.expires_at <= current:
                self._items.pop(attempt_id, None)
                raise AnthropicSubscriptionFlowError(
                    "This authorization attempt expired. Start again."
                )
            if not secrets.compare_digest(pending.state, received_state or ""):
                raise AnthropicSubscriptionFlowError(
                    "The authorization state did not match. Start again."
                )
            # Remove before exchange so concurrent submissions cannot replay it.
            self._items.pop(attempt_id, None)
            return pending

    def cancel(self, attempt_id: str, owner: Optional[str]) -> bool:
        with self._lock:
            pending = self._items.get(attempt_id)
            if pending is None or pending.owner != owner:
                return False
            self._items.pop(attempt_id, None)
            return True

    def has(self, attempt_id: str, owner: Optional[str]) -> bool:
        with self._lock:
            pending = self._items.get(attempt_id)
            return pending is not None and pending.owner == owner

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


PENDING_AUTHORIZATIONS = PendingAuthorizationStore()


def redact(value: Any) -> str:
    """Return a constant redaction marker for any OAuth secret."""
    return "[REDACTED]" if value else ""


def _refresh_lock_for(auth_id: str) -> threading.Lock:
    with _AUTH_REFRESH_LOCKS_GUARD:
        lock = _AUTH_REFRESH_LOCKS.get(auth_id)
        if lock is None:
            lock = threading.Lock()
            _AUTH_REFRESH_LOCKS[auth_id] = lock
        return lock


def _code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def start_authorization(
    owner: Optional[str], *, now: Optional[float] = None
) -> Dict[str, Any]:
    pending = PENDING_AUTHORIZATIONS.create(owner, now=now)
    query = urlencode(
        {
            "code": "true",
            "client_id": ANTHROPIC_OAUTH_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": ANTHROPIC_OAUTH_REDIRECT_URI,
            "scope": ANTHROPIC_OAUTH_SCOPES,
            "code_challenge": _code_challenge(pending.code_verifier),
            "code_challenge_method": "S256",
            "state": pending.state,
        }
    )
    return {
        "attempt_id": pending.attempt_id,
        "authorize_url": f"{ANTHROPIC_OAUTH_AUTHORIZE_URL}?{query}",
        "expires_in": ANTHROPIC_PENDING_AUTHORIZATION_SECONDS,
    }


def _parse_pasted_callback(callback: str) -> tuple[str, str]:
    pasted = (callback or "").strip()
    if not pasted:
        raise AnthropicSubscriptionFlowError(
            "Paste the authorization code returned by Claude."
        )
    if "://" in pasted:
        parsed = urlparse(pasted)
        params = parse_qs(parsed.query)
        if params.get("error"):
            raise AnthropicSubscriptionDenied(
                "Claude authorization was denied. Start again when ready."
            )
        code = (params.get("code") or [""])[0].strip()
        state = (params.get("state") or [""])[0].strip()
    else:
        code, separator, state = pasted.partition("#")
        code = code.strip()
        state = state.strip() if separator else ""
        if code in {"access_denied", "denied", "cancelled"}:
            raise AnthropicSubscriptionDenied(
                "Claude authorization was denied. Start again when ready."
            )
    if not code or not state:
        raise AnthropicSubscriptionFlowError(
            "The pasted callback is malformed. Copy the complete code#state value."
        )
    return code, state


def _oauth_error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("type") or error.get("code") or "").strip()
    return str(error or "").strip()


def _raise_for_oauth_response(response: httpx.Response, action: str) -> None:
    if response.status_code < 400:
        return
    error_code = _oauth_error_code(response)
    if response.status_code == 429:
        raise AnthropicSubscriptionRateLimited(
            "Anthropic subscription quota or rate limiting was reached. Retry later."
        )
    if response.status_code in (401, 403) or error_code in {
        "invalid_grant",
        "invalid_token",
        "refresh_token_reused",
    }:
        raise AnthropicSubscriptionReauthRequired(
            f"Anthropic subscription {action} was rejected. Reconnect the provider."
        )
    raise AnthropicSubscriptionError(
        f"Anthropic subscription {action} failed with HTTP {response.status_code}."
    )


def _token_payload(response: httpx.Response, action: str) -> Dict[str, Any]:
    _raise_for_oauth_response(response, action)
    try:
        payload = response.json()
    except Exception as exc:
        raise AnthropicSubscriptionError(
            f"Anthropic subscription {action} returned invalid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise AnthropicSubscriptionError(
            f"Anthropic subscription {action} returned an unexpected response."
        )
    return payload


def _oauth_user_agent() -> str:
    version = os.getenv("ANTHROPIC_CLI_VERSION", "").strip() or "2.1.112"
    return f"claude-cli/{version} (external, cli)"


def exchange_authorization_code(
    authorization_code: str,
    code_verifier: str,
    state: str,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    response = httpx.post(
        ANTHROPIC_OAUTH_TOKEN_URL,
        headers={
            "Content-Type": "application/json",
            "User-Agent": _oauth_user_agent(),
        },
        json={
            "grant_type": "authorization_code",
            "client_id": ANTHROPIC_OAUTH_CLIENT_ID,
            "code": authorization_code,
            "state": state,
            "redirect_uri": ANTHROPIC_OAUTH_REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        timeout=timeout,
    )
    payload = _token_payload(response, "token exchange")
    if not payload.get("access_token") or not payload.get("refresh_token"):
        raise AnthropicSubscriptionReauthRequired(
            "Anthropic subscription token exchange was incomplete. Reconnect the provider."
        )
    return payload


def complete_authorization(
    owner: Optional[str],
    attempt_id: str,
    callback: str,
    *,
    exchange: Callable[..., Dict[str, Any]] = exchange_authorization_code,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    authorization_code, received_state = _parse_pasted_callback(callback)
    pending = PENDING_AUTHORIZATIONS.consume_validated(
        (attempt_id or "").strip(),
        owner,
        received_state,
        now=now,
    )
    return exchange(
        authorization_code=authorization_code,
        code_verifier=pending.code_verifier,
        state=received_state,
    )


def refresh_oauth_tokens(
    refresh_token: str, timeout: float = 20.0
) -> Dict[str, Any]:
    if not refresh_token:
        raise AnthropicSubscriptionReauthRequired(
            "Anthropic subscription refresh credentials are missing. Reconnect the provider."
        )
    response = httpx.post(
        ANTHROPIC_OAUTH_TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _oauth_user_agent(),
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": ANTHROPIC_OAUTH_CLIENT_ID,
        },
        timeout=timeout,
    )
    payload = _token_payload(response, "token refresh")
    if not payload.get("access_token"):
        raise AnthropicSubscriptionReauthRequired(
            "Anthropic subscription refresh was incomplete. Reconnect the provider."
        )
    return payload


def token_expiry(expires_in: Any, *, now: Optional[datetime] = None) -> datetime:
    current = now or datetime.utcnow()
    try:
        seconds = max(int(expires_in), 1)
    except (TypeError, ValueError):
        seconds = 3600
    return current + timedelta(seconds=seconds)


def access_token_is_expiring(
    expires_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    skew_seconds: int = ANTHROPIC_ACCESS_TOKEN_REFRESH_SKEW_SECONDS,
) -> bool:
    if expires_at is None:
        return True
    current = now or datetime.utcnow()
    return expires_at <= current + timedelta(seconds=int(skew_seconds))


def resolve_runtime_credentials(
    auth_id: str,
    owner: Optional[str] = None,
    *,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    ProviderAuthSession, SessionLocal, utcnow_naive = _database_handles()

    with _refresh_lock_for(auth_id):
        db = SessionLocal()
        try:
            row = (
                db.query(ProviderAuthSession)
                .filter(
                    ProviderAuthSession.id == auth_id,
                    ProviderAuthSession.provider == ANTHROPIC_SUBSCRIPTION_PROVIDER,
                    ProviderAuthSession.owner == owner,
                )
                .first()
            )
            if row is None:
                raise AnthropicSubscriptionAuthNotFound(
                    "Anthropic subscription credentials were not found for this user."
                )
            access_token = row.access_token or ""
            refresh_token = row.refresh_token or ""
            if (
                force_refresh
                or not access_token
                or access_token_is_expiring(row.expires_at)
            ):
                refreshed = refresh_oauth_tokens(refresh_token)
                rotated_refresh = refreshed.get("refresh_token") or refresh_token
                if not rotated_refresh:
                    raise AnthropicSubscriptionReauthRequired(
                        "Anthropic subscription refresh credentials are missing. Reconnect."
                    )
                # Rotated access and refresh tokens are committed atomically
                # before the lock is released or any caller receives the bearer.
                row.access_token = refreshed["access_token"]
                row.refresh_token = rotated_refresh
                row.expires_at = token_expiry(
                    refreshed.get("expires_in"), now=utcnow_naive()
                )
                row.last_refresh = utcnow_naive()
                db.commit()
                db.refresh(row)
                access_token = row.access_token or ""
            if not access_token:
                raise AnthropicSubscriptionReauthRequired(
                    "Anthropic subscription credentials are incomplete. Reconnect."
                )
            return {
                "provider": ANTHROPIC_SUBSCRIPTION_PROVIDER,
                "base_url": (
                    row.base_url or DEFAULT_ANTHROPIC_SUBSCRIPTION_BASE_URL
                ).rstrip("/"),
                "api_key": access_token,
                "auth_mode": row.auth_mode or ANTHROPIC_SUBSCRIPTION_AUTH_MODE,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def anthropic_subscription_headers(access_token: Optional[str]) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
        "anthropic-beta": OAUTH_BETA,
        "User-Agent": _oauth_user_agent(),
        "x-app": "cli",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    # OAuth must never be rewritten to Anthropic's API-key transport.
    headers.pop("x-api-key", None)
    return headers


def fetch_available_models(
    access_token: str,
    *,
    timeout: float = 10.0,
) -> list[str]:
    """Return the subscription account's ordered Anthropic model inventory."""
    if not access_token:
        raise AnthropicSubscriptionReauthRequired(
            "Anthropic subscription credentials are missing. Reconnect the provider."
        )

    models: list[str] = []
    seen_models: set[str] = set()
    seen_cursors: set[str] = set()
    params: Optional[Dict[str, str]] = None

    for _ in range(20):
        response = httpx.get(
            ANTHROPIC_MODELS_URL,
            headers=anthropic_subscription_headers(access_token),
            params=params,
            timeout=timeout,
        )
        _raise_for_oauth_response(response, "model discovery")
        try:
            payload = response.json()
        except Exception as exc:
            raise AnthropicSubscriptionError(
                "Anthropic subscription model discovery returned invalid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise AnthropicSubscriptionError(
                "Anthropic subscription model discovery returned an unexpected response."
            )

        data = payload.get("data")
        if not isinstance(data, list):
            raise AnthropicSubscriptionError(
                "Anthropic subscription model discovery returned an unexpected response."
            )
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if (
                isinstance(model_id, str)
                and model_id
                and model_id not in seen_models
            ):
                seen_models.add(model_id)
                models.append(model_id)

        if not payload.get("has_more"):
            break
        cursor = str(payload.get("last_id") or "").strip()
        if not cursor or cursor in seen_cursors:
            raise AnthropicSubscriptionError(
                "Anthropic subscription model discovery returned invalid pagination."
            )
        seen_cursors.add(cursor)
        params = {"after_id": cursor}
    else:
        raise AnthropicSubscriptionError(
            "Anthropic subscription model discovery exceeded its page limit."
        )

    return models


def is_anthropic_subscription_headers(headers: Any) -> bool:
    if not isinstance(headers, dict):
        return False
    authorization = next(
        (
            value
            for key, value in headers.items()
            if str(key).lower() == "authorization"
        ),
        "",
    )
    beta = next(
        (
            value
            for key, value in headers.items()
            if str(key).lower() == "anthropic-beta"
        ),
        "",
    )
    return (
        isinstance(authorization, str)
        and authorization.startswith("Bearer ")
        and "oauth-2025-04-20" in str(beta)
    )


def _oauth_tool_name(name: str) -> str:
    value = str(name or "")
    if value.startswith("mcp_"):
        return value
    if not value:
        return value
    return f"mcp_{value[0].upper()}{value[1:]}"


def strip_oauth_tool_name(name: str) -> str:
    value = str(name or "")
    if not value.startswith("mcp_"):
        return value
    unprefixed = value[4:]
    if not unprefixed:
        return ""
    return unprefixed[0].lower() + unprefixed[1:]


def transform_oauth_messages(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the minimal Claude Code system/history transform for OAuth."""
    transformed = copy.deepcopy(payload)
    system_entries = transformed.get("system")
    if not isinstance(system_entries, list):
        system_entries = (
            [{"type": "text", "text": str(system_entries)}]
            if system_entries
            else []
        )
    moved_text = "\n\n".join(
        str(entry.get("text") or "")
        for entry in system_entries
        if isinstance(entry, dict) and entry.get("text")
    ).strip()
    transformed["system"] = [
        {"type": "text", "text": CLAUDE_CODE_SYSTEM_IDENTITY}
    ]
    messages = transformed.get("messages")
    if not isinstance(messages, list):
        messages = []
        transformed["messages"] = messages
    if moved_text:
        first_user = next(
            (message for message in messages if message.get("role") == "user"),
            None,
        )
        if first_user is not None:
            content = first_user.get("content")
            if isinstance(content, str):
                first_user["content"] = f"{moved_text}\n\n{content}"
            elif isinstance(content, list):
                content.insert(0, {"type": "text", "text": moved_text})
            else:
                first_user["content"] = [{"type": "text", "text": moved_text}]
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                block["name"] = _oauth_tool_name(block.get("name") or "")
    return transformed


def transform_oauth_tools(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Prefix tool definitions exactly once for Claude OAuth validation."""
    transformed = copy.deepcopy(payload)
    tools = transformed.get("tools")
    if not isinstance(tools, list):
        return transformed
    for tool in tools:
        if isinstance(tool, dict) and tool.get("name"):
            tool["name"] = _oauth_tool_name(tool["name"])
    return transformed


def format_inference_error(status_code: int) -> str:
    if status_code in (401, 403):
        return (
            "Anthropic subscription credentials were rejected. "
            "Reconnect the provider."
        )
    if status_code == 429:
        return (
            "Anthropic subscription quota or rate limiting was reached. "
            "Credentials may still be valid."
        )
    return f"Anthropic subscription request failed with HTTP {status_code}."


def to_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, AnthropicSubscriptionRateLimited):
        return HTTPException(429, str(exc))
    if isinstance(
        exc,
        (AnthropicSubscriptionReauthRequired, AnthropicSubscriptionAuthNotFound),
    ):
        return HTTPException(401, f"{exc} Reconnect the provider.")
    if isinstance(exc, AnthropicSubscriptionDenied):
        return HTTPException(400, str(exc))
    if isinstance(exc, AnthropicSubscriptionFlowError):
        status = 410 if "expired" in str(exc).lower() else 400
        return HTTPException(status, str(exc))
    return HTTPException(
        502, "Anthropic subscription authorization failed. Retry the connection."
    )
