#!/usr/bin/env bash
# Idempotent Cloud Agent install for the bradley-skills repository.
#
# The repo ships Markdown skills plus stdlib-only Python 3 helper scripts and
# benchmarks, so there are no third-party dependencies to install. This script:
#   1. Verifies Python 3 is available.
#   2. Links each skill into ~/.cursor/skills (Cursor Cloud Agent slash-command
#      discovery) and ~/.agents/skills (skill bodies resolve helpers here).
#   3. Byte-compiles the Python sources as a fast syntax smoke check.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ">>> python version"
python3 --version

link_skills_into() {
  local dest="$1"
  mkdir -p "$dest"
  local skill name
  for skill in "$REPO_ROOT"/skills/*/; do
    name="$(basename "$skill")"
    ln -sfn "${skill%/}" "$dest/$name"
  done
}

echo ">>> linking skills into ~/.cursor/skills and ~/.agents/skills"
link_skills_into "$HOME/.cursor/skills"
link_skills_into "$HOME/.agents/skills"

echo ">>> byte-compiling python sources"
python3 -m compileall -q skills benchmarks

echo ">>> install complete"
