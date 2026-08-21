---
name: agent-organization-directory
description: Define, validate, snapshot, and inspect Bradley's privacy-safe provider-neutral agent organization directory. Use when changing exact task-to-role bindings, primary reportsTo edges, reparenting or host-placement revisions, observer subscriptions, or advertised contact capabilities. This skill validates organization metadata; it does not own task lifecycle or message delivery.
---

# Agent Organization Directory

Maintain the versioned organization metadata that lets agents discover exact
provider tasks, their roles, their one primary authority parent, and advertised
contact capabilities without turning the directory into a command bus.

The normative contract is
[`references/directory-schema-v1.md`](references/directory-schema-v1.md). Use
the stdlib helper for every local validation, snapshot, lookup, or reparenting
change:

```sh
python3 scripts/agent_directory.py validate fixtures/directory-v1.json
python3 scripts/agent_directory.py snapshot fixtures/directory-v1.json --output /tmp/agent-directory-snapshot.json
python3 scripts/agent_directory.py lookup /tmp/agent-directory-snapshot.json \
  --directory fixtures/directory-v1.json \
  --identity 'codex:01a0233b-65c0-7972-9ced-3e9b55ef6486:local'
```

## Working Rules

- Identity is exact `provider + taskId + hostScope`. Titles, display names,
  Linear parentage, and Notion page names never identify a task.
- Every active non-root binding has exactly one active primary `reportsTo`
  identity. A root is an exact task binding whose `reportsTo` is null; the
  generic root role reports to Bradley/the user outside the task tree.
- Reparenting or moving the current host creates one superseding binding
  revision and execution epoch. Apply it only after exact destination readback.
- Reparent or revoke every active child before revoking its parent. A directory
  with an active child pointing at a revoked parent is invalid and intentionally
  cannot be used as the starting point for another operation.
- Startup, resume, and compaction consume the same validated snapshot revision.
  Fork or recovery creation gets a new exact task identity. FABLE-391 owns the
  Codex lifecycle hook that consumes this contract.
- Observer subscriptions and contact routes are discovery metadata. They do not
  add authority edges, transfer scope, prove provider readiness, or authorize a
  recipient to act. Recipients revalidate evidence and authority independently.
- Keep the durable source in the verified Agent Workspace and produce bounded
  local snapshots for synchronous consumers. No turn depends on a live Notion
  request. Verify every snapshot against its cached validated directory before
  lookup; structure-only snapshot validation does not prove correspondence.
- Store only the fields admitted by the schema. Raw transcripts, prompts,
  messages, tool output, credentials, user content, and provider payloads are
  outside this contract.

## Reparenting

Use a two-step proposal/readback/application flow. `propose-reparent` emits a
frozen proposal whose digest can be acknowledged by the destination provider.
`apply-reparent` requires a matching destination readback before it supersedes
the prior active binding. Stale directory revisions, mismatched digests, denied
readback, cycles, and multi-parent results fail closed.

The helper never contacts a provider. Provider adapters may produce the
readback object, but adapter capability and live task state remain native
provider facts.

## Non-Goals

This skill does not implement lifecycle state, heartbeats, dispatch, task
creation, message delivery, retries, provider substitution, raw transcript
storage, merge, deploy, release, production, or tracker authority.
