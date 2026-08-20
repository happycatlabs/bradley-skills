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

## Workflow

1. Classify the request as retrieve, create, reorganize, or update.
2. Verify the destination guard.
3. Search beneath the exact configured root before creating anything. Fetch
   plausible matches and prefer the canonical existing project page.
4. Choose the smallest durable shape:
   - update a section for a bounded note;
   - create a subpage for a topic with an independent lifecycle or likely
     future updates;
   - create a project page only when no canonical page exists.
5. Before writes, read the current page. Preserve useful content, links, child
   pages, and the user's organization. Prefer targeted updates or appends over
   whole-page replacement.
6. Read back every changed page and verify its title, parent, content, and URL.
7. Report the canonical page URL and a concise list of changes.

Never create a page merely to log that an agent ran. Avoid duplicate project
roots, per-session pages, routine heartbeat logs, and speculative hierarchies.

## Project And Domain Pages

When asked to establish durable context for a project or domain lead:

1. Search only beneath the configured root for the exact name and close
   variants.
2. Select the canonical page from its content and ancestry, not title alone.
3. Create the project page directly beneath the root only when no canonical
   page exists.
4. Store stable scope, role contracts, architecture, decisions, and links to
   live authorities. Do not claim that a registered task is currently active.
5. Link tickets, PRs, repositories, provider task ids, and evidence rather than
   copying their full contents.

Use clear subject titles rather than run ids. Put dates inside pages only when
chronology matters.

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
