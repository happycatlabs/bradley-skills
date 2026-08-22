#!/usr/bin/env bash
# Per-boot Cloud Agent start. Writes the machine-local Agent Workspace
# profile from environment secrets when present. Missing secrets are not a
# start failure — the skill's destination guard stops before Notion I/O.
set -euo pipefail

profile_path="${AGENT_WORKSPACE_PROFILE:-${XDG_CONFIG_HOME:-$HOME/.config}/bradley-skills/agent-workspace.json}"

if [[ -z "${AGENT_WORKSPACE_JSON:-}" ]]; then
  echo ">>> no AGENT_WORKSPACE_JSON; skip profile write"
  exit 0
fi

mkdir -p "$(dirname "$profile_path")"
umask 077
printf '%s\n' "$AGENT_WORKSPACE_JSON" > "$profile_path"
chmod 600 "$profile_path"
python3 -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$profile_path"
echo ">>> wrote agent-workspace profile"
