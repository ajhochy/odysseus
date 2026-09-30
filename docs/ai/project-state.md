# Project State

## Current focus

Prepare the Anthropic subscription OAuth model-inventory repair for human
review. The connected account now supplies its model catalog dynamically, and
all models exposed by that catalog have been exercised through Odysseus.

## Active branch / PR

- Branch: `workflow/run-2026-07-28-anthropic-oauth`
- Fork target: `ajhochy/odysseus`
- PR: none; merge decisions remain with a human reviewer.

## In progress

- Final commit, fork push, and fork CI inspection.

## Risks / known issues

- Anthropic subscription OAuth remains an experimental compatibility surface
  and may change independently of Odysseus.
- The original broader live criterion still lacks a real Anthropic API-key
  control account; the unchanged API-key path is covered by the complete
  repository suite.
- On macOS, the full suite must use `TMPDIR=/private/tmp` so Unix socket paths
  stay short and `/tmp` does not diverge from its canonical `/private/tmp`
  identity.

## Test status

- Static Python compilation and JavaScript syntax checks passed.
- Focused OAuth/catalog suites: 254 passed.
- Acceptance c10/c11: 2 passed.
- Issue and PR gates: 4,800 passed, 4 skipped each.
- Fresh-server probes: `/api/health` healthy; redacted subscription status
  connected with 11 provider-advertised models.
- Gated live test refreshed the catalog, matched endpoint state, and received a
  non-empty real stream from every advertised model without a 404 or safe error
  event.
- Original OAuth UI evidence: [provider setup](evidence/anthropic-subscription-setup.png)
  and [connected admin state](evidence/anthropic-subscription-admin.png).

## Next step

Commit and push the branch to the fork, inspect any triggered fork CI, then
hand the branch to a human reviewer without merging it.

## Consolidation 2026-09-29
- Branch: `mega/2026-09-29-consolidation` (from `fork/dev` 25a4d13; owned remote is `fork` = ajhochy/odysseus, `origin` = pewdiepie-archdaemon/odysseus is read-only and untouched). PR: PR_URL_PLACEHOLDER. Issues are disabled on this fork, so the tracking content lives in the PR body.
- Folded: `workflow/run-2026-07-28-anthropic-oauth` (tip 8741063 = WIP snapshot over fed54b0: experimental Anthropic subscription OAuth, live-verification docs, dynamic model discovery). The snapshot recorded six `static/js/editor/build/*.js` files as deleted (collateral of a 2026-09-16 build-dir cleanup; `.gitignore` un-ignores that directory, they are source files), so they are restored from `fork/dev` in a follow-up commit. Carried from `wip/odysseus-2026-09-29` (4fb4f13, snapshot of the main checkout on `dev`): the GitNexus block appended to `AGENTS.md` and the new `CLAUDE.md`.
- Dropped (reasons; all tips are in the bundle `~/Documents/.consolidation-backups/odysseus-2026-09-29.bundle`):
  - local `dev` / `unpushed-main-2026-09-29` (87407b3): pristine 2026-06-23 clone of upstream dev; upstream since rewrote history, 1552 of 1553 patches are patch-equivalent in `fork/dev` and the last one (18f29bd) has 198526e.
  - `wip/odysseus-2026-09-29` (4fb4f13): based on that old clone; only AGENTS.md/CLAUDE.md content carried, the six build/ deletions are not applied.
  - `fork/dependabot/github_actions/actions-b93032d1f2` (f5d62f7) and `fork/dependabot/pip/python-258f0448df` (85a6839): upstream dependabot dependency-bump commits, mirrors of the same SHAs on `origin`.
  - `fork/discovery` (53ce950, 12 docs commits by Alexandre Teixeira) and `fork/fix/add-directory-event-loop` (e222e92, 2 commits by StressTestor): third-party upstream branches, mirrors of the same SHAs on `origin`, not user work.
  - `fork/feature/tbench-bounded-read-guard` (d8a2059): ancestor of `fork/dev`.
- Keep exception (judgment call): `fork/main` (cf4e240) is the upstream release line (default is `dev`); it is neither folded nor deleted.
- In-flight worktrees: none (no live process has a cwd in `~/Documents/odysseus-anthropic-oauth`). Its ignored `.env` and `data/` (live OAuth test state) are archived at `~/Documents/.consolidation-backups/odysseus--odysseus-anthropic-oauth--ignored-files-2026-09-29.tar.gz` before the cleanup script removes the worktree.
- Cleanup script (not yet run): `~/Documents/.consolidation-backups/cleanup/odysseus-2026-09-29-cleanup.sh`.
