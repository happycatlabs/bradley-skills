# Bradley Skills

Personal agent skills for launching, inspecting, coordinating, and reviewing
multi-agent development work.

## Skills

- `claude` and `codex`: provider-specific subagent launchers
- `inspect-claude-session`, `inspect-codex-session`, and
  `inspect-cursor-session`: local session transcript inspection
- `orchestrate`: parallel multi-agent coordination
- `engineering-lead`: interruptible portfolio, project, and domain coordination
- `agent-workspace`: machine-configured durable Notion context for agent teams
- `agent-organization-directory`: provider-neutral role/reporting directory and bounded local snapshots
- `material-transition-outbox`: quiet-by-default, restart-safe reporting to exact directory bindings
- `workspace-coordinator`: live reconciliation across workspace, tasks,
  trackers, repositories, CI, and shipping gates
- `dispatch`: durable Codex worktree handoffs and delegation ledgers
- `monitor`: PR-aware supervision and durable task closeout
- `codex-automation`: local and remote Codex automation lifecycle management
- `brainstorm` and `consult`: cross-agent exploration and consultation
- `critique`: bounded review loops over existing work

## Install

### Cursor Cloud Agents

This repo is a Cursor / Agent plugin (`plugin.json` and
`.cursor-plugin/plugin.json`). The source trees live under `skills/`. Cursor
does **not** load a bare `skills/` directory as slash commands.

Cloud Agents discover project skills from `.cursor/skills/` (and
`.agents/skills/`) in the checkout at session start. Each entry there is a
symlink to the matching `skills/<name>` tree so `/agent-workspace` and the
rest show up without a plugin install.

User-level discovery on the VM is `~/.cursor/skills` (Cursor) and
`~/.agents/skills` (helper paths skill bodies mention). The Cloud Agent
install script links both. Laptop `~/.cursor/skills` does **not** sync to
Cloud Agents.

To use the skills on other repositories, install the plugin on your Cursor
account (Plugins → add this GitHub repo, or Team Marketplace **Required**).

### Local symlink (Claude, Codex, laptop Cursor)

Symlink each directory under `skills/` into `~/.agents/skills/`:

```sh
for skill in skills/*; do
  ln -sfn "$PWD/$skill" "$HOME/.agents/skills/$(basename "$skill")"
done
```

Each skill is self-contained. Keep helper scripts and `agents/openai.yaml`
metadata beside its `SKILL.md` when changing or distributing a skill.

## Agent Workspace Setup

Each machine uses its own Agent Workspace destination. The repository contains
no Notion workspace id, page id, user identity, or canonical workspace link.
After installing the skills, create this machine-local profile:

```json
{
  "schemaVersion": 1,
  "provider": "notion",
  "workspaceId": "<this-machine-notion-workspace-id>",
  "rootPageId": "<this-machine-agent-workspace-page-id>",
  "rootPageUrl": "<optional-canonical-notion-url>",
  "profileName": "<optional-local-name>"
}
```

The default profile is
`${XDG_CONFIG_HOME:-$HOME/.config}/bradley-skills/agent-workspace.json`.
Set `AGENT_WORKSPACE_PROFILE` to an absolute path to use a different local
profile. Keep the file outside repositories and readable only by the current
user. The target agent runtime must separately expose and authenticate its
Notion workspace, tracker, and live task-provider connectors. The skills stop
before Notion operations when the configured workspace and exact root page
cannot be verified.

To establish a project or domain lead on that machine, assign the session the
role explicitly and invoke `engineering-lead`. It uses `agent-workspace` for
durable context, `workspace-coordinator` for live reconciliation, `dispatch`
for durable owners, `monitor` for observation, and `orchestrate` for bounded
leaf work. Record stable role and project context beneath that machine's
configured Agent Workspace; keep task activity, tickets, code, CI, and shipping
truth with their native authorities.
