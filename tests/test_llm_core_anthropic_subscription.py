"""Anthropic subscription request-shape tests at the real LLM boundary."""

import asyncio
import json

from src import anthropic_subscription as subscription
from src import llm_core


class _SyncResponse:
    is_success = True
    status_code = 200

    def json(self):
        return {"content": [{"type": "text", "text": "ok"}]}


def _messages():
    return [
        {"role": "system", "content": "Application instructions"},
        {"role": "user", "content": "Hello"},
    ]


def test_sync_oauth_transport_applies_bearer_and_system_transform(monkeypatch):
    captured = {}
    monkeypatch.setattr(llm_core, "_get_cached_response", lambda _key: None)
    monkeypatch.setattr(llm_core, "_set_cached_response", lambda *_args: None)

    def fake_post(url, headers, **kwargs):
        captured.update({"url": url, "headers": headers, **kwargs})
        return _SyncResponse()

    monkeypatch.setattr(llm_core, "httpx_post_kimi_aware", fake_post)
    result = llm_core.llm_call(
        "https://api.anthropic.com/v1/messages",
        "claude-sonnet-4-6",
        _messages(),
        headers=subscription.anthropic_subscription_headers(
            "synthetic-access"
        ),
    )

    assert result == "ok"
    assert captured["headers"]["Authorization"] == "Bearer synthetic-access"
    assert "x-api-key" not in captured["headers"]
    assert (
        captured["json"]["system"][0]["text"]
        == subscription.CLAUDE_CODE_SYSTEM_IDENTITY
    )
    assert captured["json"]["messages"][0]["content"].startswith(
        "Application instructions\n\n"
    )


def test_sync_api_key_transport_remains_untransformed(monkeypatch):
    captured = {}
    monkeypatch.setattr(llm_core, "_get_cached_response", lambda _key: None)
    monkeypatch.setattr(llm_core, "_set_cached_response", lambda *_args: None)

    def fake_post(url, headers, **kwargs):
        captured.update({"url": url, "headers": headers, **kwargs})
        return _SyncResponse()

    monkeypatch.setattr(llm_core, "httpx_post_kimi_aware", fake_post)
    result = llm_core.llm_call(
        "https://api.anthropic.com/v1/messages",
        "claude-sonnet-4-6",
        _messages(),
        headers={
            "x-api-key": "synthetic-api-key",
            "anthropic-version": "2023-06-01",
        },
    )

    assert result == "ok"
    assert captured["headers"]["x-api-key"] == "synthetic-api-key"
    assert "Authorization" not in captured["headers"]
    assert "anthropic-beta" not in captured["headers"]
    assert (
        captured["json"]["system"][0]["text"]
        == "Application instructions"
    )


class _StreamResponse:
    def __init__(self, lines, status_code=200, body=b""):
        self.lines = lines
        self.status_code = status_code
        self.body = body

    async def aiter_lines(self):
        for line in self.lines:
            yield line

    async def aread(self):
        return self.body


class _StreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_args):
        return False


class _StreamClient:
    def __init__(self, response, captured):
        self.response = response
        self.captured = captured

    def stream(self, method, url, **kwargs):
        self.captured.update({"method": method, "url": url, **kwargs})
        return _StreamContext(self.response)


def _stream(monkeypatch, response):
    captured = {}
    monkeypatch.setattr(
        llm_core,
        "_get_http_client",
        lambda: _StreamClient(response, captured),
    )
    monkeypatch.setattr(llm_core, "_is_host_dead", lambda _url: False)
    monkeypatch.setattr(llm_core, "note_model_activity", lambda *_a, **_k: None)
    monkeypatch.setattr(llm_core, "_clear_host_dead", lambda *_a, **_k: None)

    async def drive():
        chunks = []
        async for chunk in llm_core.stream_llm(
            "https://api.anthropic.com/v1/messages",
            "claude-sonnet-4-6",
            _messages(),
            headers=subscription.anthropic_subscription_headers(
                "synthetic-access"
            ),
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "description": "Read",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        ):
            chunks.append(chunk)
        return chunks

    return captured, asyncio.run(drive())


def test_stream_oauth_transport_transforms_tools_and_restores_tool_name(
    monkeypatch,
):
    response = _StreamResponse(
        [
            "data: "
            + json.dumps(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "mcp_Read_file",
                    },
                }
            ),
            "data: "
            + json.dumps(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": "{}",
                    },
                }
            ),
            "data: " + json.dumps({"type": "message_stop"}),
        ]
    )
    captured, chunks = _stream(monkeypatch, response)

    assert captured["headers"]["Authorization"] == "Bearer synthetic-access"
    assert "x-api-key" not in captured["headers"]
    assert captured["json"]["tools"][0]["name"] == "mcp_Read_file"
    assert (
        captured["json"]["system"][0]["text"]
        == subscription.CLAUDE_CODE_SYSTEM_IDENTITY
    )
    events = "\n".join(chunks)
    assert '"name": "read_file"' in events
    assert '"name": "mcp_Read_file"' not in events


def test_stream_oauth_error_does_not_return_upstream_body(monkeypatch):
    response = _StreamResponse(
        [],
        status_code=401,
        body=b'{"error":"synthetic-access secret body"}',
    )
    _captured, chunks = _stream(monkeypatch, response)
    output = "\n".join(chunks)

    assert "Reconnect" in output
    assert "synthetic-access secret body" not in output
