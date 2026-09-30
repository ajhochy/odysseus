"""Anthropic subscription runtime resolution and bearer persistence tests."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import (
    Base,
    ModelEndpoint,
    ProviderAuthSession,
    Session as DbSession,
)
import routes.chat_helpers as chat_helpers
from src import anthropic_subscription as subscription
import src.endpoint_resolver as resolver


def _mem_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(resolver, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(chat_helpers, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(
        subscription,
        "_database_handles",
        lambda: (ProviderAuthSession, TestSessionLocal, datetime.utcnow),
    )
    return TestSessionLocal


def _seed(TestSessionLocal):
    db = TestSessionLocal()
    db.add(
        ProviderAuthSession(
            id="anth-auth",
            provider=subscription.ANTHROPIC_SUBSCRIPTION_PROVIDER,
            owner="alice",
            base_url="https://api.anthropic.com",
            access_token="synthetic-live-access",
            refresh_token="synthetic-refresh",
            expires_at=datetime.utcnow() + timedelta(hours=1),
            auth_mode=subscription.ANTHROPIC_SUBSCRIPTION_AUTH_MODE,
        )
    )
    db.add(
        ModelEndpoint(
            id="anth-endpoint",
            name="Anthropic Subscription",
            base_url="https://api.anthropic.com",
            owner="alice",
            provider_auth_id="anth-auth",
            is_enabled=True,
            api_key=None,
        )
    )
    db.commit()
    endpoint = db.query(ModelEndpoint).filter_by(id="anth-endpoint").one()
    db.expunge(endpoint)
    db.close()
    return endpoint


def test_runtime_resolution_preserves_oauth_bearer_header_separation(monkeypatch):
    TestSessionLocal = _mem_db(monkeypatch)
    endpoint = _seed(TestSessionLocal)

    base, credential = resolver.resolve_endpoint_runtime(endpoint, owner="alice")
    headers = resolver.build_headers(credential, base)

    assert base == "https://api.anthropic.com"
    assert credential == "synthetic-live-access"
    assert credential.auth_mode == "anthropic-subscription"
    assert headers["Authorization"] == "Bearer synthetic-live-access"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "oauth-2025-04-20" in headers["anthropic-beta"]
    assert "x-api-key" not in headers

    with pytest.raises(subscription.AnthropicSubscriptionAuthNotFound):
        resolver.resolve_endpoint_runtime(endpoint, owner="bob")


def test_anthropic_api_key_header_path_is_unchanged():
    headers = resolver.build_headers(
        "synthetic-api-key", "https://api.anthropic.com"
    )
    assert headers == {
        "x-api-key": "synthetic-api-key",
        "anthropic-version": "2023-06-01",
    }


def test_subscription_bearer_is_request_local_not_plaintext_session_state(
    monkeypatch,
):
    TestSessionLocal = _mem_db(monkeypatch)
    _seed(TestSessionLocal)
    db = TestSessionLocal()
    db.add(
        DbSession(
            id="session-1",
            name="chat",
            endpoint_url="https://api.anthropic.com/v1/messages",
            model="claude-sonnet-4-6",
            owner="alice",
            headers={},
        )
    )
    db.commit()
    db.close()

    credential = resolver.RuntimeCredential(
        "synthetic-live-access", "anthropic-subscription"
    )
    monkeypatch.setattr(
        resolver,
        "resolve_endpoint_runtime",
        lambda endpoint, owner=None: ("https://api.anthropic.com", credential),
    )
    session = SimpleNamespace(
        id="session-1",
        endpoint_url="https://api.anthropic.com/v1/messages",
        model="claude-sonnet-4-6",
        owner="alice",
        headers={},
    )

    chat_helpers.resolve_session_auth(
        session, "session-1", owner="alice"
    )

    assert session.headers["Authorization"] == "Bearer synthetic-live-access"
    db = TestSessionLocal()
    persisted = db.query(DbSession).filter_by(id="session-1").one()
    assert persisted.headers == {}
    db.close()
