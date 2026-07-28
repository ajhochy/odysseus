# Failure Patterns

## 2026-07-28 — Issue 0 — OAuth start response shape escaped the contract

- **Result**: smoke FAIL (verification claimed FAIL)
- **Category**: C2 — wrong contract; final live completion also blocked by C5 external CAPTCHA
- **Criteria affected**: issue-0-c1, issue-0-c9
- **Root cause**: The UI mock used `authorization_url` while the real backend emitted `authorize_url`; after correcting that integration mismatch, Anthropic required hCaptcha before callback exchange.
- **Suggested fix**: Keep the backend's canonical response shape in the UI contract and resume the gated live smoke after human CAPTCHA interaction.
