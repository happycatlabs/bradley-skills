---
name: agent-workspace
description: Maintain a machine-configured Notion Agent Workspace as durable shared context for projects and agent teams. Use when creating, updating, organizing, retrieving, or summarizing architecture, decisions, plans, research, role contracts, project notebooks, or privacy-safe handoffs that should survive across machines and sessions. The destination comes from a local profile; never infer it from a page title or repository copy.
---

# Agent Workspace

Maintain the configured human-and-agent knowledge space without turning it
into a transcript archive, command bus, or second issue tracker.

## Destination Profile

The destination is machine-local. Never embed a workspace id, page id, URL,
email address, or provider identity in this skill or a repository artifact.

Resolve the profile in this order:

1. `AGENT_WORKSPACE_PROFILE`, when set to an absolute JSON file path.
2. `${XDG_CONFIG_HOME:-$HOME/.config}/bradley-skills/agent-workspace.json`.

The profile contract is:

```json
{
  "schemaVersion": 1,
  "provider": "notion",
  "workspaceId": "<workspace UUID>",
  "rootPageId": "<Agent Workspace page UUID>",
  "rootPageUrl": "<optional canonical Notion URL>",
  "profileName": "<optional local display name>"
}
```

`workspaceId` and `rootPageId` are required exact identifiers. The URL and
display name are conveniences, not authorities. Keep the local profile out of
repositories and restrict its file permissions to the current user.

If the profile is missing, malformed, or does not match the connected Notion
identity and exact root page, stop before any Notion read, search, or write.
Explain how to configure it. Do not search by title, select a similarly named
page, or fall back to a destination from another machine.

## Destination Guard

Before every Notion read or write:

1. Load and validate the machine-local profile.
2. Fetch the connected Notion identity and confirm the exact `workspaceId`.
3. Fetch `rootPageId` (or its canonical URL when configured) and confirm both
   the page id and its workspace ancestry.
4. Limit searches and page traversal to that exact root.

If the Notion connector cannot prove either identity, stop. Do not initiate a
login, change accounts, or modify the profile unless the user explicitly asks.
Read-only access is not a reason to weaken the destination guard.

## Choose The Right Home

- **Agent Workspace:** durable project context, architecture, decisions,
  plans, research, operating notes, role contracts, and concise handoffs.
- **Tracker:** structured accepted work whose status and next action should be
  easy to scan.
- **Linear:** actionable work with priority, acceptance criteria, assignment,
  dependencies, or lifecycle state.
- **GitHub:** code, review, CI, and merge evidence.
- **Repository:** enforceable contracts, versioned technical docs, tests, and
  agent guidance that must change with code.
- **Worklog/task history:** discovery of prior sessions and execution history.
  Link the relevant task; do not copy its transcript into Notion.

One fact may be linked across systems, but each system keeps its authority. A
Notion note does not close a ticket, approve a PR, prove deployment, or replace
a repository contract.

## Workspace Layout

The information model is stable; the Notion layout is not. A workspace may use
nested pages, databases, or a mix. Preserve the configured workspace's existing
shape unless the user asks to reorganize it.

Agents must be able to resolve:

- execution environments and routing scopes;
- exact provider task bindings and environment placement;
- stable project and domain scope;
- decisions, architecture, plans, research, role contracts, operating notes,
  and concise handoffs.

Read [references/workspace-layouts.md](references/workspace-layouts.md) when
creating or reorganizing a workspace, registering an agent or environment, or
writing a structured handoff. It defines required meaning and layout choices,
not one universal hierarchy.

Do not hardcode database, data-source, page, agent, environment, or provider
identifiers in this skill. Resolve every destination beneath the guarded root
and confirm its content, schema when applicable, and ancestry. A title alone is
not authority.

## Workflow

1. Classify the request as retrieve, create, reorganize, or update.
2. Verify the destination guard.
3. Fetch the current hierarchy beneath the root. Search only beneath that root
   before creating anything. Fetch plausible matches and prefer the canonical
   existing page or database record.
4. Choose the smallest durable shape:
   - update a section for a bounded note;
   - create a subpage for a topic with its own context or likely future updates;
   - use a database record when several items share stable fields, relations,
     or query needs;
   - create a new container only when the current layout has no suitable home.
5. Before writes, read the current page. Preserve useful content, links, child
   pages, and the user's organization. Prefer targeted updates or appends over
   whole-page replacement.
6. Read back every changed page and verify its title, parent, content, and URL.
7. Report the canonical page URL and a concise list of changes.

Never create a page merely to log that an agent ran. Avoid duplicate project
roots, per-session pages, routine heartbeat logs, and speculative hierarchies.

## Project And Domain Pages

When asked to establish durable context for a project or domain lead:

1. Search the existing project area or database for the exact subject and close
   variants.
2. Select the canonical page or record from its properties, content, relations,
   and ancestry, not its title alone.
3. Create a project subpage or database record only when no canonical home
   exists. Follow the workspace's current layout.
4. Connect the project to its exact registered lead binding when known. In a
   database layout use a relation; in a page layout use a compact identity link
   or structured section.
5. Store architecture, decisions, plans, research, and handoffs where the
   workspace already keeps shared context. Use child pages when subjects need
   room; use records when repeated fields and cross-project queries matter.
6. Link tickets, pull requests, repositories, provider task ids, and evidence
   rather than copying their full contents.

Use clear subject titles rather than run ids. Put dates inside pages only when
chronology matters.

## Environments And Agent Bindings

Keep environment, adapter, and task identity separate:

- An environment says where execution occurs and which routing scope applies.
- An adapter is one environment's authenticated way to inspect or contact a
  provider. Installing an adapter on a Mac does not make a cloud agent local.
- An agent binding is exactly `provider + taskId + hostScope`, associated with
  one environment. Names and role labels are descriptive only.

Register only verified identities. Record provider-advertised contact
capabilities, but do not infer that a task is running, loaded, reachable, or
unfinished. The native provider owns those facts. When placement or reporting
changes, supersede the old binding rather than silently editing its identity.

## Handoffs

Write a handoff page, section, or record only for material context that a
different agent, provider, or environment needs to continue. Follow the current
workspace layout. Include the project, source and destination bindings or
environments when known, verified facts, settled decisions, remaining question
or next gate, and links to native evidence. Do not put live status, routine
heartbeats, raw messages, or transcripts in the handoff.

## Content, Privacy, And Safety

- Lead with the current understanding or decision, then evidence and links.
- Separate verified facts, inferences, decisions, questions, and next steps.
- Keep summaries compact enough to scan and sufficient for an agent on another
  machine to continue without the original transcript.
- Preserve why a decision was made, its scope, and its revisit condition.
- Update canonical pages instead of appending contradictory snapshots.
- Fetch the provider's current formatting specification before using extended
  Notion markdown; do not guess unsupported syntax.
- Never store secrets, auth material, raw private chats, raw prompts, provider
  payloads, user messages, emails, IP addresses, or unnecessary personal data.
- Do not delete, archive, move, or replace a hierarchy without explicit user
  authority.

## Reporting

For a write:

```text
Updated: <page or hierarchy>
Changed: <sections or subpages>
Notion: <canonical URL>
```

For a read-only request, summarize and link the canonical pages. Do not dump
the full workspace.
