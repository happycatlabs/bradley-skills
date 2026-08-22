#!/usr/bin/env bash
# Idempotent Cloud Agent install for the bradley-skills repository.
#
# The repo ships Markdown skills plus stdlib-only Python 3 helper scripts and
# benchmarks, so there are no third-party dependencies to install. This script:
#   1. Verifies Python 3 is available.
#   2. Links each skill into ~/.agents/skills so skill bodies resolve their
#      helpers via ~/.agents/skills/... (see README).
#   3. Byte-compiles the Python sources as a fast syntax smoke check.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ">>> python version"
python3 --version

echo ">>> linking skills into ~/.agents/skills"
skills_dest="$HOME/.agents/skills"
mkdir -p "$skills_dest"
for skill in "$REPO_ROOT"/skills/*/; do
  name="$(basename "$skill")"
  ln -sfn "${skill%/}" "$skills_dest/$name"
done

echo ">>> byte-compiling python sources"
python3 -m compileall -q skills benchmarks

echo ">>> install complete"
