# Testing Guide

## Baseline and focused checks

```bash
python -m compileall -q app.py core routes src services scripts tests
python -m pytest -q
```

JavaScript syntax:

```bash
find static/js -name '*.js' -print0 | xargs -0 -n1 node --check
node --check static/app.js
```

## Provider auth checks

Run focused OAuth, endpoint-resolution, model-route, and LLM transport tests
before the full suite. Network/token exchange tests must mock secrets unless a
deliberate live smoke is being run with an already authenticated local account.

## Live smoke

Start the app using the normal local environment, verify its health endpoint,
complete provider sign-in in a browser, send a minimal prompt, and confirm a
streamed response. Never print or commit access/refresh tokens.
