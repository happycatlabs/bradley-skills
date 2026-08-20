# Bradley Skills

Personal agent skills for launching, inspecting, coordinating, and reviewing
multi-agent development work.

## Skills

- `claude` and `codex`: provider-specific subagent launchers
- `inspect-claude-session`, `inspect-codex-session`, and
  `inspect-cursor-session`: local session transcript inspection
- `orchestrate`: parallel multi-agent coordination
- `engineering-lead`: interruptible portfolio, project, and domain coordination
- `dispatch`: durable Codex worktree handoffs and delegation ledgers
- `monitor`: PR-aware supervision and durable task closeout
- `codex-automation`: local and remote Codex automation lifecycle management
- `brainstorm` and `consult`: cross-agent exploration and consultation
- `critique`: bounded review loops over existing work

## Install

The skills are installed by symlinking each directory under `skills/` into
`~/.agents/skills/`:

```sh
for skill in skills/*; do
  ln -sfn "$PWD/$skill" "$HOME/.agents/skills/$(basename "$skill")"
done
```

Each skill is self-contained. Keep helper scripts and `agents/openai.yaml`
metadata beside its `SKILL.md` when changing or distributing a skill.
