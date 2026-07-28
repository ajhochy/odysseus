#!/usr/bin/env python3
"""Repository-local workflow control plane for Odysseus."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv/bin/python") if (ROOT / ".venv/bin/python").exists() else (
    shutil.which("python3.11") or sys.executable
)
CONTEXT_FILES = (
    "AGENTS.md",
    "docs/ai/project-state.md",
    "docs/ai/repo-map.md",
    "docs/ai/architecture.md",
    "docs/ai/testing-guide.md",
    "docs/ai/current-plan.md",
    "docs/ai/decisions.md",
)


def run(command: list[str]) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONPYCACHEPREFIX", "/tmp/odysseus-ai-workflow-pycache")
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


def status(_args: argparse.Namespace) -> int:
    missing = [path for path in CONTEXT_FILES if not (ROOT / path).exists()]
    print(f"Repo root: {ROOT}")
    if missing:
        print("Missing workflow context files:")
        for path in missing:
            print(f"- {path}")
        return 1
    print("Workflow context: ready")
    return 0


def checks(args: argparse.Namespace) -> int:
    commands = [
        [PYTHON, "-m", "compileall", "-q", "app.py", "core", "routes",
         "src", "services", "scripts", "tests"],
        [PYTHON, "-m", "pytest", "-q"],
    ]
    if args.level == "pr":
        commands.append(["node", "--check", "static/app.js"])
        js_files = sorted((ROOT / "static/js").rglob("*.js"))
        commands.extend([["node", "--check", str(path)] for path in js_files])
    for command in commands:
        code = run(command)
        if code:
            return code
    return 0


def next_issue(_args: argparse.Namespace) -> int:
    print("No repository-specific issue selector is configured.")
    return 0


def start_issue(args: argparse.Namespace) -> int:
    branch = f"issue-{args.issue}"
    print(f"Would create branch: {branch}")
    return run(["git", "switch", "-c", branch]) if args.execute else 0


def open_pr(args: argparse.Namespace) -> int:
    command = ["gh", "pr", "create", "--draft", "--title", args.title,
               "--body", "See branch commits and docs/ai/project-state.md."]
    print(" ".join(command))
    return run(command) if args.execute else 0


def run_flow(args: argparse.Namespace) -> int:
    print(f"Workflow request: {args.issue or 'free-form'}")
    return checks(argparse.Namespace(level=args.check_level))


def smoke_prompt(_args: argparse.Namespace) -> int:
    print("Launch: python app.py")
    print("Checklist:")
    print("- GET the documented health endpoint and confirm HTTP 200.")
    print("- Connect the target provider without exposing credentials.")
    print("- Send a minimal prompt and confirm a non-empty streamed response.")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("status").set_defaults(func=status)
    checks_parser = sub.add_parser("checks")
    checks_parser.add_argument("--level", choices=("issue", "smoke", "pr"), required=True)
    checks_parser.set_defaults(func=checks)
    next_parser = sub.add_parser("next-issue")
    next_parser.add_argument("--milestone")
    next_parser.set_defaults(func=next_issue)
    start_parser = sub.add_parser("start-issue")
    start_parser.add_argument("--issue", required=True)
    start_parser.add_argument("--execute", action="store_true")
    start_parser.set_defaults(func=start_issue)
    pr_parser = sub.add_parser("open-pr")
    pr_parser.add_argument("--title", required=True)
    pr_parser.add_argument("--execute", action="store_true")
    pr_parser.set_defaults(func=open_pr)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--issue")
    run_parser.add_argument("--execute", action="store_true")
    run_parser.add_argument("--after")
    run_parser.add_argument("--check-level", choices=("issue", "smoke", "pr"), default="issue")
    run_parser.add_argument("--pr-title")
    run_parser.set_defaults(func=run_flow)
    sub.add_parser("smoke-prompt").set_defaults(func=smoke_prompt)
    return result


if __name__ == "__main__":
    args = parser().parse_args()
    raise SystemExit(args.func(args))
