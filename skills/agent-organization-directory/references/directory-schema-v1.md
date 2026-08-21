# Agent Organization Directory V1

Normative keywords such as MUST and MUST NOT are intentional.

## Authority Boundary

The directory is privacy-safe organization metadata. It describes exact task
identity, role, scope, one primary reporting edge, current host placement,
observer visibility, and advertised contact capability. The live provider owns
task existence and lifecycle. Linear owns accepted work, GitHub owns code and
pull-request truth, and the verified Agent Workspace owns durable role and
architecture context.

The directory MUST NOT be used as a task lifecycle database, message broker,
heartbeat log, dispatch engine, provider substitute, or authority grant.

## Versions

- Directory: `bradley.agent-organization-directory/v1`
- Binding: `bradley.agent-organization-binding/v1`
- Observer subscription: `bradley.agent-observer-subscription/v1`
- Local snapshot: `bradley.agent-organization-snapshot/v1`
- Reparent proposal: `bradley.agent-organization-reparent-proposal/v1`
- Destination readback: `bradley.agent-organization-destination-readback/v1`
- Conformance fixture: `bradley.agent-organization-conformance/v1`

Unknown versions or fields fail closed. V1 bounds a directory to 256 binding
records, 128 active bindings, 512 observer subscriptions, 32 advertised
capabilities per binding, 4 KiB per string, and 256 KiB per serialized local
snapshot.

The snapshot byte limit applies to the exact serialized file, including
whitespace, and is checked before JSON parsing. Snapshot writes check the exact
bytes they will emit and immediately read back the same bounded file.

## Exact Identity

Every binding and task reference uses exactly:

```json
{
  "provider": "codex",
  "taskId": "019fabe3-6424-7583-997d-0b93afc18972",
  "hostScope": "local"
}
```

All three fields are non-empty and MUST NOT contain wildcards. `hostScope` is
the stable routing/isolation scope for the binding. `placement.currentHostId`
is the current provider host or sandbox lease location and may change only in a
superseding revision after destination readback.

Names, titles, labels, Notion pages, Linear relations, and repository paths are
never identity aliases.

## Directory

```json
{
  "schemaVersion": "bradley.agent-organization-directory/v1",
  "directoryRevision": 1,
  "sourceReadback": {
    "provider": "notion",
    "workspaceId": "...",
    "rootPageId": "...",
    "pageId": "...",
    "pageUrl": "https://app.notion.com/p/...",
    "observedAt": "2026-08-21T09:11:07.724Z"
  },
  "bindings": [],
  "observerSubscriptions": []
}
```

`sourceReadback` is a privacy-safe receipt that the exact durable Agent
Workspace page was read. It carries identifiers and observation time only, not
page content or provider payloads. A local snapshot is a validated projection;
it never replaces the durable source.

## Binding History

Each binding record contains:

- exact `identity`;
- positive `bindingRevision` and `executionEpoch`;
- `state`: `active`, `superseded`, or `revoked`;
- `root`: boolean;
- `role`: `machine_engineering_lead`, `engineering_lead`, `project_lead`,
  `domain_lead`, `delivery_owner`, `exploration_owner`, `watcher`,
  `leaf_worker`, or `leaf_scout`;
- `scope`: `team`, `project`, optional `domain`, absolute/URL
  `contractRef`, `authorityRef`, and `privacyClass`;
- `placement.currentHostId`;
- `reportsTo`: null for a root or one exact identity for a non-root;
- `issuedAt`;
- `supersedes`: null for revision 1, otherwise the immediately prior revision,
  epoch, and content digest; and
- closed-list `advertisedCapabilities`.

Revisions for one identity are contiguous. Every historical record except the
latest is `superseded`. The latest is either `active` or `revoked`. At most one
record per identity is active. A superseding revision increments both
`bindingRevision` and `executionEpoch` by one. Reasserting context after
startup, resume, or compaction does not create a revision.

`issuedAt` increases strictly with each binding revision. Before revoking a
binding, every active child that reports to it MUST first be reparented or
revoked. Revoking the parent first creates an invalid missing-recipient state;
V1 fails closed instead of guessing a repair edge.

Every active non-root binding MUST resolve to exactly one active parent. Active
edges MUST form a forest: multiple intentional roots are allowed, but cycles,
missing recipients, and multi-parent authority are rejected.

`privacyClass` is `public_metadata`, `internal_metadata`, or
`restricted_metadata`. All classes use the same bounded field set; the class is
an access-policy label, not permission to embed raw private content.

## Discovery And Contact

Advertised capability names are:

- `inspect_task`
- `message_existing_task`
- `resume_task`
- `create_recovery_task`
- `interrupt_task`
- `archive_task`

Capability status is one of `live_proven`, `source_proven`,
`documented_only`, `desired`, or `unsupported`. A `routeRef` is allowed only
for `live_proven`; unsupported or unproven entries carry null. The local helper
returns `capability_unsupported` unless the exact recipient advertises the
requested capability as `live_proven` with a route.

This proves only advertised contact metadata. It does not prove current worker
readiness or authorize the sender, transport, or recipient action.

## Observer Subscriptions

An observer subscription contains exact `subscriber` and `observes`
identities, a positive revision, `active` or `revoked` state, one of
`portfolio_visibility`, `matrix_visibility`, or `material_transition`, and the
literal `authority: false`. Both identities must resolve while the subscription
is active. A subscription never becomes a `reportsTo` edge.

Revisions are contiguous per exact subscriber + observes + purpose
relationship. Every historical revision is revoked and only the latest may be
active. A directory or snapshot with multiple active revisions of the same
observer relationship fails closed.

Bounded cross-team messages may carry evidence or dependency facts. The
recipient MUST revalidate native authority before action, and no message or
visibility relationship transfers scope or mutation authority.

## Reparent And Host-Move Protocol

1. Validate the current directory and resolve the exact target and destination
   parent.
2. Freeze a proposal against `baseDirectoryRevision` and the previous binding
   digest. The proposed record increments binding revision and execution epoch.
   Its parent, current host, issued time, revision, epoch, state, and
   supersession fence are the only fields that may differ from the current
   binding; role, scope, root status, identity, and advertised capabilities are
   copied exactly.
3. Obtain provider-supplied destination readback for the proposal digest,
   proposed binding digest, exact target identity, destination host, revision,
   and epoch.
4. Apply only an accepted exact match while the base directory and previous
   binding remain unchanged.
5. Mark the old record `superseded`, append the proposed active record,
   increment `directoryRevision`, validate the complete forest, and read back
   the written local snapshot.

Failed or missing readback leaves the directory unchanged. The stdlib helper
validates supplied evidence but does not contact providers or implement their
lifecycle.

## Local Snapshot

The snapshot contains only active bindings, active observer subscriptions,
the source readback, `directoryRevision`, and a SHA-256 digest of the canonical
directory. Entries are deterministically sorted. Consumers validate the
snapshot before lookup and use exact identity only.

Consumers MUST verify `directoryRevision`, `directoryDigest`, and the complete
snapshot projection against the cached validated directory before lookup. A
well-shaped snapshot alone does not prove freshness or correspondence. The
`snapshot --output` command immediately re-reads and verifies the written file.

Snapshot validation is synchronous and local. Notion availability, titles,
summarized context, message visibility, and another provider's tools MUST NOT
affect resolution.
