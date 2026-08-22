#!/usr/bin/env bash
# Run every Python unittest suite in the repository.
#
# Each suite loads its sibling module via importlib and must run from its own
# directory, so `unittest discover` from the repo root finds nothing. This
# script executes each `test_*.py` from its containing directory and aggregates
# the results.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

mapfile -t test_files < <(find skills benchmarks -type f -name 'test_*.py' | sort)

if [[ ${#test_files[@]} -eq 0 ]]; then
  echo "No test files found." >&2
  exit 1
fi

failed=()
for test_file in "${test_files[@]}"; do
  dir="$(dirname "$test_file")"
  module="$(basename "${test_file%.py}")"
  echo ">>> ${test_file}"
  if ! (cd "$dir" && python3 -m unittest "$module"); then
    failed+=("$test_file")
  fi
done

echo
if [[ ${#failed[@]} -gt 0 ]]; then
  echo "FAILED suites: ${failed[*]}" >&2
  exit 1
fi
echo "All ${#test_files[@]} test suites passed."
