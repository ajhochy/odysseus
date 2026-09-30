# Follow-up: make workspace-confinement assertion path-alias safe on macOS

## Failure

`tests/test_workspace_confine.py::test_glob_confined_e2e` fails on macOS when
temporary paths are spelled with `/tmp` but `os.path.realpath()` canonicalizes
the workspace to `/private/tmp`.

## Repro Command

```bash
TMPDIR=/tmp .venv/bin/python -m pytest -q \
  tests/test_workspace_confine.py::test_glob_confined_e2e -vv
```

## Expected

The escaping glob returns the not-found message without reporting a discovered
outside file.

## Actual

The tool correctly returns `No files`, but the assertion
`secret not in r["output"]` fails because the echoed relative pattern contains
the non-canonical `/tmp/.../secret.txt` spelling as a substring when rendered
under the canonical `/private/tmp/...` workspace.

## Relevant Output

The isolated diagnostic showed:

- `ws`: `/tmp/<temporary>`
- `os.path.realpath(ws)`: `/private/tmp/<temporary>`
- `rel`: `../../../tmp/<outside>/secret.txt`
- the original `/tmp/<outside>/secret.txt` is consequently a substring of the
  expected not-found message.

The same test and assertion are present byte-for-byte on clean `origin/dev` at
`25a4d13`; the Anthropic OAuth branch does not modify this file.

## Likely Cause

The test compares differently normalized path spellings rather than the
security behavior. This is a deterministic macOS `/tmp` symlink-alias issue,
not a glob-confinement escape.

## Likely Files

- `tests/test_workspace_confine.py`

## Required Fix

Canonicalize both compared paths, or assert that the output contains no actual
matched-result entry while allowing the documented echo of the caller-supplied
pattern.

## Required Tests / Evaluation

- Run the isolated test on macOS.
- Run `tests/test_workspace_confine.py` on macOS and Linux.
- Run the repository PR check.

Priority: P2, test portability. This is intentionally outside the Anthropic
subscription OAuth change.
