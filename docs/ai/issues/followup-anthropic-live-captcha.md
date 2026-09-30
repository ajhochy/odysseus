# Follow-up: finish account-gated Anthropic subscription live smoke

## Failure

The isolated Odysseus app reached Anthropic's signed-in OAuth consent page,
but Anthropic required hCaptcha before returning the pasted authorization
callback.

## Repro Command

1. Launch Odysseus with an isolated `ODYSSEUS_DATA_DIR`.
2. Select **Claude Subscription (experimental)** in Settings.
3. Start the connection and authorize the signed-in Claude account.
4. Complete the presented hCaptcha.
5. Paste the returned callback into Odysseus.
6. Run:

```bash
ODYSSEUS_ANTHROPIC_LIVE=1 \
ODYSSEUS_LIVE_BASE_URL=http://127.0.0.1:7147 \
.venv/bin/python -m pytest -q \
  tests/live/test_anthropic_subscription_live.py
```

## Expected

OAuth completion provisions the endpoint and the live test observes a
non-empty streamed response containing `ODYSSEUS_LIVE_OK`.

## Actual

Health, readiness, Admin UI, `/setup`, and the real Claude consent page were
verified. Callback exchange and inference could not proceed without human
CAPTCHA interaction, which automation must not bypass.

## Required Evaluation

- Complete the CAPTCHA and pasted-code flow.
- Run the gated live inference test.
- Force one safe token refresh and confirm the rotated token is persisted.
- If an Anthropic API key is available, run one live API-key control request.

Priority: P1 verification blocker. This is not evidence of a product-code
failure and must not be reported as a passed smoke until completed.
