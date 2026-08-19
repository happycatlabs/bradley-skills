#!/usr/bin/env python3
"""Benchmark critique context selection and finding signal on a disposable repo."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "benchmarks" / "runs"
SKILL = REPO / "skills" / "critique" / "SKILL.md"

EXIT_RULE = "RULE-EXIT-CONTRACT"
TEST_RULE = "RULE-TEST-TIERS"
DECOY_RULE = "RULE-UI-STYLING"

SCHEMA = {
    "type": "object",
    "properties": {
        "context_used": {"type": "array", "items": {"type": "string"}},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "trigger": {"type": "string"},
                    "evidence": {"type": "string"},
                    "impact": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["file", "line", "trigger", "evidence", "impact", "fix"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["context_used", "findings"],
    "additionalProperties": False,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)


def make_fixture(root: Path) -> Path:
    fixture = root / "fixture"
    (fixture / "src").mkdir(parents=True)
    (fixture / "web").mkdir()
    (fixture / "AGENTS.md").write_text(
        "# Repository guidance\n\n"
        f"- {EXIT_RULE}: Commands that emit a result with `ok: false` must exit nonzero.\n"
        f"- {TEST_RULE}: Pre-commit runs unit tests only; CLI exit behavior requires a focused integration test.\n"
    )
    (fixture / "web" / "AGENTS.md").write_text(
        "# Web-only guidance\n\n"
        f"- {DECOY_RULE}: Interactive controls use the indigo focus-ring token.\n"
    )
    (fixture / "src" / "cli.py").write_text(
        "import json\n"
        "import sys\n\n\n"
        "def emit_result(result: dict[str, object]) -> None:\n"
        "    print(json.dumps(result))\n\n\n"
        "def main(argv: list[str]) -> int:\n"
        "    if argv == [\"version\"]:\n"
        "        emit_result({\"ok\": True, \"version\": \"1.0\"})\n"
        "        return 0\n"
        "    return 2\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    raise SystemExit(main(sys.argv[1:]))\n"
    )
    git(fixture, "init", "-q")
    git(fixture, "add", ".")
    committed = git(
        fixture,
        "-c",
        "user.name=Benchmark",
        "-c",
        "user.email=benchmark@example.invalid",
        "commit",
        "-qm",
        "baseline",
    )
    if committed.returncode != 0:
        raise RuntimeError(committed.stderr.strip() or "failed to commit fixture baseline")

    (fixture / "src" / "cli.py").write_text(
        "import json\n"
        "import sys\n\n\n"
        "BADGE_LABELS = {\"alpha\": \"Alpha\", \"beta\": \"Beta\", \"gamma\": \"Gamma\"}\n\n\n"
        "def emit_result(result: dict[str, object]) -> None:\n"
        "    print(json.dumps(result))\n\n\n"
        "def format_badge_labels(keys: list[str]) -> list[str]:\n"
        "    return [label for key, label in BADGE_LABELS.items() if key in keys]\n\n\n"
        "def inspect() -> dict[str, object]:\n"
        "    return {\"ok\": False, \"labels\": format_badge_labels([\"alpha\"])}\n\n\n"
        "def main(argv: list[str]) -> int:\n"
        "    if argv == [\"version\"]:\n"
        "        emit_result({\"ok\": True, \"version\": \"1.0\"})\n"
        "        return 0\n"
        "    if argv == [\"inspect\"]:\n"
        "        emit_result(inspect())\n"
        "        return 0\n"
        "    return 2\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    raise SystemExit(main(sys.argv[1:]))\n"
    )
    return fixture


def build_prompt() -> str:
    return f"""You are the adjudicating reviewer in a benchmark. Do not spawn or consult other agents.

Follow this critique skill exactly for context selection and finding admission:

--- BEGIN CRITIQUE SKILL ---
{SKILL.read_text()}
--- END CRITIQUE SKILL ---

Review only the current uncommitted diff in this disposable repository. Read the changed-file list and applicable repo guidance yourself. Return only the schema-constrained result.

For `context_used`, list the exact rule identifiers that actually govern the changed surface. For every admitted finding, provide the responsible source file and line plus the reachable trigger, exact evidence, concrete impact, and bounded fix. Omit suggestions that fail the skill's admission gate.
"""


def parse_payload(stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        outer = json.loads(stdout)
    except json.JSONDecodeError:
        return {}, {}
    if not isinstance(outer, dict):
        return {}, {}
    structured = outer.get("structured_output")
    if isinstance(structured, str):
        try:
            structured = json.loads(structured)
        except json.JSONDecodeError:
            structured = {}
    return outer, structured if isinstance(structured, dict) else {}


def score_response(exit_code: int, outer: dict[str, Any], response: dict[str, Any]) -> dict[str, bool]:
    context = "\n".join(str(item) for item in response.get("context_used", []))
    findings = response.get("findings", [])
    if not isinstance(findings, list):
        findings = []
    valid_findings = [finding for finding in findings if isinstance(finding, dict)]
    defect_surfaced = any(
        finding.get("file") == "src/cli.py"
        and "exit" in text.lower()
        and ("ok" in text.lower() or "false" in text.lower())
        for finding in valid_findings
        for text in [
            " ".join(
                str(finding.get(key, ""))
                for key in ("file", "trigger", "evidence", "impact", "fix")
            )
        ]
    )
    required_fields = ("file", "line", "trigger", "evidence", "impact", "fix")
    contract_complete = bool(findings) and all(
        isinstance(finding, dict)
        and all(finding.get(field) not in (None, "") for field in required_fields)
        for finding in findings
    )
    noise_terms = ("linear scan", "performance", "optimization", "optimize", "complexity", "inefficient", "o(n)")
    noise_surfaced = any(
        term
        in " ".join(
            str(finding.get(key, "")) for key in ("trigger", "impact", "fix")
        ).lower()
        for finding in valid_findings
        for term in noise_terms
    )
    return {
        "exit_zero": exit_code == 0,
        "json_parses": bool(response),
        "session_id": bool(outer.get("session_id")),
        "context_selected": EXIT_RULE in context and TEST_RULE in context,
        "decoy_excluded": DECOY_RULE not in context,
        "defect_surfaced": defect_surfaced,
        "noise_suppressed": not noise_surfaced,
        "finding_contract_complete": contract_complete,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="haiku", help="Claude model alias used for the read-only lane.")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = RUNS / f"{timestamp}-critique-signal"
    root.mkdir(parents=True)
    fixture = make_fixture(root)
    prompt = build_prompt()
    command = [
        "claude",
        "-p",
        "--safe-mode",
        "--permission-mode",
        "plan",
        "--model",
        args.model,
        "--effort",
        "low",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(SCHEMA),
        prompt,
    ]
    (root / "prompt.txt").write_text(prompt)
    (root / "command.txt").write_text(shlex.join(command[:-1]) + " <prompt>\n")
    # Zero-context diffs avoid single-space context markers, so the evidence
    # artifact itself remains clean if a maintainer intentionally stages it.
    (root / "fixture.diff").write_text(
        git(fixture, "diff", "--no-ext-diff", "--unified=0").stdout
    )
    write_json(
        root / "manifest.json",
        {
            "started_at": now_iso(),
            "repo": str(REPO),
            "model": args.model,
            "python": sys.version,
            "claude_version": subprocess.run(
                ["claude", "--version"], text=True, capture_output=True, check=False
            ).stdout.strip(),
        },
    )

    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=fixture,
            text=True,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        completed = subprocess.CompletedProcess(command, 124, exc.stdout or "", exc.stderr or "timeout")
    wall_seconds = time.monotonic() - started
    (root / "stdout.log").write_text(completed.stdout or "")
    (root / "stderr.log").write_text(completed.stderr or "")
    outer, response = parse_payload(completed.stdout or "")
    write_json(root / "response.json", response)
    checks = score_response(completed.returncode, outer, response)
    scorecard = {
        "completed_at": now_iso(),
        "classification": "PASS" if all(checks.values()) else "FAIL",
        "wall_seconds": wall_seconds,
        "exit_code": completed.returncode,
        "session_id": str(outer.get("session_id") or ""),
        "checks": checks,
    }
    write_json(root / "scorecard.json", scorecard)
    report = [
        "# Critique signal benchmark",
        "",
        f"- Result: {scorecard['classification']}",
        f"- Model: {args.model}",
        f"- Wall time: {wall_seconds:.1f}s",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    report.extend(f"| {name} | {'PASS' if passed else 'FAIL'} |" for name, passed in checks.items())
    (root / "report.md").write_text("\n".join(report) + "\n")
    shutil.rmtree(fixture, ignore_errors=True)
    print(root)
    print(json.dumps(scorecard, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
