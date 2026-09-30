"""Owner-scoped Anthropic subscription route/provisioning regressions."""

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, ModelEndpoint, ProviderAuthSession
import routes.anthropic_subscription_routes as routes
from src import anthropic_subscription as subscription


def _mem_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(routes, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(
        subscription,
        "fetch_available_models",
        lambda *_args, **_kwargs: list(
            subscription.CURATED_ANTHROPIC_SUBSCRIPTION_MODELS
        ),
    )
    return TestSessionLocal


def _tokens(access="synthetic-access", refresh="synthetic-refresh"):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": 3600,
    }


def test_provision_reconnects_same_owner_without_duplicate_endpoint(monkeypatch):
    TestSessionLocal = _mem_db(monkeypatch)
    first = routes._provision_endpoint(_tokens(), "alice")
    db = TestSessionLocal()
    endpoint = db.query(ModelEndpoint).filter(ModelEndpoint.owner == "alice").one()
    endpoint.pinned_models = json.dumps(
        ["claude-sonnet-5", "claude-haiku-3-5"]
    )
    endpoint.hidden_models = json.dumps(["claude-haiku-3-5"])
    db.commit()
    db.close()

    second = routes._provision_endpoint(
        _tokens("synthetic-new-access", "synthetic-new-refresh"), "alice"
    )

    assert first["id"] == second["id"]
    assert first["models"] == list(
        subscription.CURATED_ANTHROPIC_SUBSCRIPTION_MODELS
    )
    assert "access_token" not in first
    assert "refresh_token" not in first

    db = TestSessionLocal()
    auth_rows = (
        db.query(ProviderAuthSession)
        .filter(ProviderAuthSession.owner == "alice")
        .all()
    )
    endpoints = (
        db.query(ModelEndpoint).filter(ModelEndpoint.owner == "alice").all()
    )
    assert len(auth_rows) == 1
    assert len(endpoints) == 1
    assert auth_rows[0].access_token == "synthetic-new-access"
    assert auth_rows[0].refresh_token == "synthetic-new-refresh"
    assert auth_rows[0].expires_at > datetime.utcnow()
    assert auth_rows[0].auth_mode == "anthropic-subscription"
    assert endpoints[0].api_key is None
    assert endpoints[0].provider_auth_id == auth_rows[0].id
    assert endpoints[0].model_refresh_mode == "manual"
    assert endpoints[0].is_enabled is True
    db.close()


def test_status_is_redacted_and_owner_scoped(monkeypatch):
    _mem_db(monkeypatch)
    routes._provision_endpoint(_tokens(), "alice")

    alice = routes._status("alice")
    bob = routes._status("bob")

    assert alice["connected"] is True
    assert alice["endpoint"]["models"]
    assert "synthetic" not in repr(alice)
    assert bob == {"connected": False, "experimental": True}


def test_reconnect_adopts_discovered_inventory_and_keeps_last_good_on_failure(
    monkeypatch,
):
    TestSessionLocal = _mem_db(monkeypatch)
    first_inventory = ["claude-opus-5", "claude-sonnet-5"]
    second_inventory = ["claude-fable-5", "claude-opus-4-8"]
    inventories = iter([first_inventory, second_inventory])
    monkeypatch.setattr(
        subscription,
        "fetch_available_models",
        lambda *_args, **_kwargs: next(inventories),
    )

    first = routes._provision_endpoint(_tokens(), "alice")
    second = routes._provision_endpoint(
        _tokens("synthetic-new-access", "synthetic-new-refresh"), "alice"
    )

    assert first["models"] == first_inventory
    assert second["models"] == second_inventory

    def fail(*_args, **_kwargs):
        raise RuntimeError("safe model discovery failure")

    monkeypatch.setattr(subscription, "fetch_available_models", fail)
    retained = routes._provision_endpoint(
        _tokens("synthetic-third-access", "synthetic-third-refresh"), "alice"
    )
    assert retained["id"] == first["id"]
    assert retained["models"] == second_inventory

    db = TestSessionLocal()
    endpoint = db.query(ModelEndpoint).filter(ModelEndpoint.owner == "alice").one()
    assert endpoint.cached_models == json.dumps(second_inventory)
    assert endpoint.pinned_models is None
    assert endpoint.hidden_models is None
    db.close()


def test_disconnect_only_removes_callers_subscription_resources(monkeypatch):
    TestSessionLocal = _mem_db(monkeypatch)
    alice = routes._provision_endpoint(_tokens(), "alice")
    bob = routes._provision_endpoint(
        _tokens("synthetic-bob-access", "synthetic-bob-refresh"), "bob"
    )
    db = TestSessionLocal()
    db.add(
        ModelEndpoint(
            id="anthropic-api-key",
            name="Anthropic API key",
            base_url="https://api.anthropic.com",
            owner="alice",
            api_key="synthetic-api-key",
            is_enabled=True,
        )
    )
    db.commit()
    db.close()

    result = routes._disconnect("alice")
    assert result["disconnected"] is True
    assert result["removed_endpoint_ids"] == [alice["id"]]

    db = TestSessionLocal()
    assert (
        db.query(ModelEndpoint).filter(ModelEndpoint.id == alice["id"]).first()
        is None
    )
    assert (
        db.query(ProviderAuthSession)
        .filter(ProviderAuthSession.owner == "alice")
        .first()
        is None
    )
    assert (
        db.query(ModelEndpoint).filter(ModelEndpoint.id == bob["id"]).first()
        is not None
    )
    assert (
        db.query(ProviderAuthSession)
        .filter(ProviderAuthSession.owner == "bob")
        .first()
        is not None
    )
    api_key = (
        db.query(ModelEndpoint)
        .filter(ModelEndpoint.id == "anthropic-api-key")
        .one()
    )
    assert api_key.api_key == "synthetic-api-key"
    db.close()


def test_router_exposes_ui_contract():
    router = routes.setup_anthropic_subscription_routes()
    methods_by_path = {
        route.path: route.methods
        for route in router.routes
        if hasattr(route, "methods")
    }
    assert methods_by_path[
        "/api/anthropic-subscription/oauth/start"
    ] == {"POST"}
    assert methods_by_path[
        "/api/anthropic-subscription/oauth/complete"
    ] == {"POST"}
    assert methods_by_path["/api/anthropic-subscription/status"] == {"GET"}
    assert methods_by_path[
        "/api/anthropic-subscription/connection"
    ] == {"DELETE"}
