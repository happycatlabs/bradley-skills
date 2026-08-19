#!/usr/bin/env python3
"""Run Claude Code print mode with safer defaults for Codex skills."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


DEFAULT_ADVISORY_PROMPT = (
    "You are being consulted by Codex for an advisory second opinion. "
    "Unless the user prompt explicitly asks you to act, do not modify files, "
    "stage changes, commit, install packages, or run destructive commands. "
    "Give a direct answer, call out uncertainty, and keep the response focused."
)


def resolve_mode(args: argparse.Namespace) -> str:
    selected = [args.bare, args.safe_mode, args.project]
    if sum(1 for item in selected if item) > 1:
        raise ValueError("Use only one of --bare, --safe-mode, or --project.")
    if args.bare:
        return "bare"
    if args.safe_mode:
        return "safe"
    if args.project:
        return "project"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "bare"
    return "safe"


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt.strip()
    return sys.stdin.read().strip()


def read_schema(schema_arg: Optional[str]) -> Optional[str]:
    if not schema_arg:
        return None
    path = Path(schema_arg).expanduser()
    if path.exists():
        return path.read_text()
    return schema_arg


def build_command(args: argparse.Namespace, prompt: str) -> list[str]:
    cmd = ["claude"]
    mode = resolve_mode(args)
    if mode == "bare":
        cmd.append("--bare")
    elif mode == "safe":
        cmd.append("--safe-mode")

    if args.continue_latest:
        cmd.append("--continue")
    if args.resume:
        cmd.extend(["--resume", args.resume])
    if args.session_id:
        cmd.extend(["--session-id", args.session_id])
    if args.name:
        cmd.extend(["--name", args.name])

    cmd.extend(["-p", prompt])
    cmd.extend(["--output-format", args.output_format])

    if args.budget is not None:
        cmd.extend(["--max-budget-usd", str(args.budget)])

    schema = read_schema(args.schema)
    if schema:
        cmd.extend(["--json-schema", schema])

    if args.model:
        cmd.extend(["--model", args.model])
    if args.effort:
        cmd.extend(["--effort", args.effort])
    system_prompts = []
    if not args.no_default_system_prompt:
        system_prompts.append(DEFAULT_ADVISORY_PROMPT)
    if args.append_system_prompt:
        system_prompts.append(args.append_system_prompt)
    if system_prompts:
        cmd.extend(["--append-system-prompt", "\n\n".join(system_prompts)])

    return cmd


def normalize_payload(stdout: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ask Claude Code through non-interactive `claude -p`."
    )
    parser.add_argument("--prompt", help="Prompt text. Defaults to stdin.")
    parser.add_argument(
        "--cwd",
        default=".",
        help="Working directory for the Claude process. Defaults to current dir.",
    )
    parser.add_argument(
        "--project",
        action="store_true",
        help="Load normal Claude project context/settings. Mutually exclusive with --bare/--safe-mode.",
    )
    parser.add_argument(
        "--bare",
        action="store_true",
        help="Force --bare. Best with ANTHROPIC_API_KEY/apiKeyHelper auth.",
    )
    parser.add_argument(
        "--safe-mode",
        action="store_true",
        help="Force --safe-mode. Uses normal Claude auth while disabling customizations.",
    )
    parser.add_argument(
        "--budget",
        default=None,
        help="Value for --max-budget-usd. Default: omitted. Use a value only when you want a hard cap.",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "text", "stream-json"],
        default="json",
        help="Claude output format. Default: json.",
    )
    parser.add_argument("--schema", help="JSON schema string or path.")
    parser.add_argument("--model", help="Optional Claude model/alias.")
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="Optional Claude effort level.",
    )
    parser.add_argument("--append-system-prompt", help="Extra system guidance.")
    parser.add_argument(
        "--no-default-system-prompt",
        action="store_true",
        help="Do not append the built-in advisory/read-only system prompt.",
    )
    parser.add_argument(
        "--continue-latest",
        action="store_true",
        help="Continue the most recent conversation in this cwd.",
    )
    parser.add_argument("--resume", help="Resume a Claude session id or name.")
    parser.add_argument("--session-id", help="Force a specific UUID session id.")
    parser.add_argument("--name", help="Display name for the Claude session.")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print Claude stdout directly instead of normalized JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command that would run, without invoking Claude.",
    )
    args = parser.parse_args()

    try:
        mode = resolve_mode(args)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2

    if args.continue_latest and args.resume:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Use either --continue-latest or --resume, not both.",
                },
                indent=2,
            )
        )
        return 2

    if args.budget == "":
        args.budget = None

    prompt = read_prompt(args)
    if not prompt:
        print(json.dumps({"ok": False, "error": "No prompt provided."}, indent=2))
        return 2

    claude_path = shutil.which("claude")
    if not claude_path:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "`claude` CLI not found on PATH.",
                },
                indent=2,
            )
        )
        return 127

    cwd = Path(args.cwd).expanduser().resolve()
    if not cwd.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Working directory does not exist: {cwd}",
                },
                indent=2,
            )
        )
        return 2

    cmd = build_command(args, prompt)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "cwd": str(cwd),
                    "claude": claude_path,
                    "mode": mode,
                    "command": cmd,
                },
                indent=2,
            )
        )
        return 0

    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if args.raw or args.output_format != "json":
        sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        return proc.returncode

    payload, parse_error = normalize_payload(proc.stdout)
    if proc.returncode != 0:
        print(
            json.dumps(
                {
                    "ok": False,
                    "returncode": proc.returncode,
                    "session_id": payload.get("session_id") if payload else None,
                    "result": payload.get("result") if payload else None,
                    "raw": payload,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "parse_error": parse_error,
                },
                indent=2,
            )
        )
        return proc.returncode

    if payload is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Claude returned non-JSON output.",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "parse_error": parse_error,
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "session_id": payload.get("session_id"),
                "result": payload.get("result"),
                "structured_output": payload.get("structured_output"),
                "total_cost_usd": payload.get("total_cost_usd"),
                "duration_ms": payload.get("duration_ms"),
                "raw": payload,
                "stderr": proc.stderr,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
