# Failure Patterns

## 2026-07-28 — Issue 0 — OAuth start response shape escaped the contract

- **Result**: smoke FAIL (verification claimed FAIL)
- **Category**: C2 — wrong contract; final live completion also blocked by C5 external CAPTCHA
- **Criteria affected**: issue-0-c1, issue-0-c9
- **Root cause**: The UI mock used `authorization_url` while the real backend emitted `authorize_url`; after correcting that integration mismatch, Anthropic required hCaptcha before callback exchange.
- **Suggested fix**: Keep the backend's canonical response shape in the UI contract and resume the gated live smoke after human CAPTCHA interaction.

## 2026-07-29 — Issue 0 — Static subscription catalog advertised invalid models

- **Result**: smoke FAIL (verification claimed FAIL)
- **Category**: C2 — the setup contract passed without proving that its advertised model IDs were current and callable
- **Criteria affected**: issue-0-c1
- **Root cause**: Odysseus provisioned a hard-coded Anthropic subscription model list that had drifted from the models accepted by the live OAuth Messages endpoint.
- **Suggested fix**: Resolve or validate the catalog through the authenticated provider boundary and live-test every advertised model, not just one hard-coded default.
