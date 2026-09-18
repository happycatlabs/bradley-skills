# Agent Workspace layouts

Use this reference when creating, reorganizing, or writing structured context
in the configured Agent Workspace. Resolve live destinations beneath the
guarded root before every read or write.

## Pick a shape from the work

Use nested pages when context is narrative, the collection is small, or the
human browsing hierarchy matters most. Use databases when many items share
stable fields, agents need reliable filters or relations, or the collection
will grow across projects and environments. A mixed layout is often right.

Do not migrate a workspace merely to make it resemble another machine. Preserve
the current shape unless the user asks for a reorganization or the layout can no
longer express the required identity, environment, or context boundaries.

The same meanings must remain discoverable in every layout.

## Environments

An environment record or page identifies one execution or routing scope. Keep:

- a clear label and kind such as local machine, cloud, remote host, worktree,
  or sandbox;
- provider routing or host scope;
- privacy-safe adapter or routing information, never credentials;
- configuration state and last verification when those facts can drift;
- an explanation of what runs there and which native provider owns live state.

A local adapter that reaches a cloud service does not make the cloud agents
local. Record the adapter as an access route and the cloud service as its own
environment.

## Agent bindings

An agent binding is organization metadata, not lifecycle state. Keep:

- descriptive name and stable role;
- exact provider, task ID, and host scope;
- environment placement;
- stable scope and one reporting parent when applicable;
- binding state such as registered, superseded, or revoked;
- provider-proven contact capabilities and last verification when useful.

The exact identity is `provider + taskId + hostScope`. Do not resolve by title,
role, project, or Notion page. Registered does not mean active. Contact
capabilities do not grant authority to use them.

In a database layout, use typed properties and relations. In a page layout, use
a consistent compact identity block and link to the environment and parent
pages.

## Projects and domains

A project or domain page or record keeps:

- canonical subject name and kind;
- exact lead binding;
- stable ownership scope;
- repository, tracker, and other native authority links;
- membership state and last review when those facts can drift.

Project pages may contain their own durable context when that is the natural
workspace shape. Split context into child pages when a subject has its own
lifecycle or becomes hard to scan. In a database layout, relate substantial
context records back to the project.

## Shared context and handoffs

Durable context may be a page, a section, or a database record. Keep a clear
subject, type, project and environment scope, current or superseded state, last
verification when relevant, and the strongest native evidence links.

Lead with the current conclusion or decision. Then record the reasoning that
must survive, revisit conditions, remaining question or next gate, and links.
Update the canonical context when the conclusion changes.

Handoffs add source and destination agent bindings or environments when known.
They contain only enough verified context for another agent to continue. Do not
copy raw transcripts, prompts, messages, or provider payloads.

## Authority boundaries

- Provider tasks own live task state and messages.
- Local Work owns accepted work, ownership, current status, and next actions.
- Linear owns prioritized product work and acceptance criteria.
- GitHub and CI own code, review, pull requests, and delivery evidence.
- Repositories own enforceable technical contracts and versioned guidance.
- Agent Workspace owns durable organization and context across those systems.
