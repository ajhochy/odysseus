# Repository Agent Guide

Read `docs/ai/project-state.md`, `docs/ai/current-plan.md`, and
`docs/ai/testing-guide.md` before changing source.

- Work on a feature branch; never push directly to `dev` or `main`.
- Keep provider credentials, OAuth tokens, local databases, logs, and `.env`
  files out of Git.
- Add focused regression tests for provider/authentication behavior.
- Run the issue and PR checks documented in `docs/ai/testing-guide.md`.
- Update `docs/ai/project-state.md` and relevant decision records after a
  verified change.
- Leave merge decisions to a human reviewer.
