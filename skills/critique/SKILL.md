---
name: critique
description: "Run a bounded multi-agent critique of existing work, concrete design choices, uncommitted code, committed diffs, or another agent/session's output. Use when the user says /critique, asks for a review/stress-test/readiness check, wants Claude and Codex perspectives before committing or pushing, or asks to review dispatched/orchestrated work without low-signal findings. Prefer brainstorm for early-stage idea generation or hypothetical options. Routes differently by host agent: Codex should use Claude plus focused Codex subagents; Claude should use consult or the codex skill plus focused Claude subagents. Do not require codex-review or REVIEW.md."
---

# Critique

Use this skill to get independent pressure on existing work without treating
every finding as truth. A critique should improve correctness,
maintainability, and Agent Experience; it should not create review theater.

For early-stage ideation, use `~/.agents/skills/brainstorm/SKILL.md`
instead. Brainstorming should widen the option space before narrowing;
critique should evaluate a target that already exists.

Think of critique as a small bounded review run: decompose the review into
independent lanes, run the useful lanes in parallel when tools support it,
collect findings, and adjudicate them in the main thread. When critique is the
closeout gate for work the owning agent was already authorized to edit, that
existing edit authority includes fixing accepted findings only inside the
inherited capability and artifact/action scope. When tracker follow-up is
already authorized, ticket out-of-scope work instead of absorbing it; otherwise
mention it without creating external work. Resume the same review lanes after
each blocking-now fix or material rejection until the workflow reaches one of
the terminal states below.
The main agent is the run owner; outside reviewers are evidence sources, not
decision-makers.

Prefer a small cross-provider team over a single monolithic reviewer. Different
agent families catch different classes of issues, and splitting lanes also keeps
provider usage distributed. The normal critique flow should not depend on
`codex-review`, `REVIEW.md`, or `.review/` packets; use repo-local guidance such
as `AGENTS.md`, `CLAUDE.md`, named skills, docs, and the actual diff/code.

## Mission Lock

Critique protects the current shipping checkpoint; it does not redefine it.
The user's request is the product authority, and the primary agent owns its
execution interpretation. Reviewers do not supply product truth, acceptance
criteria, roadmap priority, or permission to expand scope. They test the frozen
mission only.

Before dispatch, record a compact mission lock:

- the user's requested outcome and the next observable shipment/proof;
- motivating examples labeled as examples, not requested features;
- the frozen artifacts and acceptance criteria being reviewed;
- explicit non-goals and forbidden external actions; and
- the allowed fix budget for this pass, including expected subsystems, public
  contracts, migrations, UI surfaces, and approximate diff size.

Adjudicate every finding into exactly one bucket:

- **Blocking now**: current code violates a frozen acceptance criterion, creates
  a regression in the reviewed change, or makes the currently authorized
  shipment/action unsafe through a concrete data-loss, credential, privacy, or
  execution path. Fix it inside the frozen scope.
- **Fast follow**: useful, real work that improves hardening, operability,
  architecture, breadth, or future autonomy but is not required for the current
  checkpoint. Record it on an existing ticket or one consolidated follow-up
  only when tracker writing is already authorized; otherwise mention it in the
  handoff. Do not edit for it, expand the review, or delay shipment.
- **Rejected**: unsupported, speculative, duplicate, or contrary to the mission.

Reviewer severity is evidence, not scope authority. A `P0` label does not make a
finding part of the MVP by itself, and a valid finding is not automatically a
blocking finding. If accepting a finding would add a subsystem, broaden provider
support, change the capability envelope, or materially increase the checkpoint's
time/complexity budget, it is a fast follow unless the user explicitly expands
scope. When unsure, preserve the mission and surface the tradeoff to the user
instead of silently moving the finish line.

The main agent must stop for user direction before accepting any finding that
introduces an unplanned UI surface, provider, public contract, table, schema,
migration, or auth/security/privacy/provenance program; grows the expected diff
past roughly twice the mission-lock budget; or requires a "technically related"
argument. A credible immediate credential, privacy, data-loss, or
production-safety path is grounds to pause and escalate, not permission for a
reviewer-designed hardening roadmap.

## Core Rules

- Reviewer lanes are always read-only. A request to "review and fix" grants the
  owning agent, not the reviewer lanes, permission to fix accepted findings
  within the owner's existing scope. A review-only request grants no edit
  authority.
- Choose and freeze the target manifest's membership and closeout claims before
  dispatch: every durable artifact, decision, external mutation, deployed
  resource, and code/diff the claim depends on. Record the initial artifact
  revision, then append an immutable revision after each accepted fix or other
  material change; do not overwrite the earlier review target. Default to the
  current diff/worktree only for code-only work. If the target is another child
  thread, prior session, or workflow behavior, first inspect it and include the
  compact operational brief in the manifest.
- Treat all outside findings as signal, not authority. The main agent must
  adjudicate them against the repo, current code, user constraints, and
  applicable repo guidance.
- Code must stay clean, explicit, organized, and maintainable. Do not accept
  cleverness, dense code, or unnecessary abstraction as "fine" unless it clearly
  improves readability, testability, extensibility, or operation.
- Prefer source-backed findings with concrete triggers. Delete hedged findings
  that boil down to "maybe someday."
- Prefer parallel independent lanes over one vague "thoughts?" pass when the
  environment supports it. Good lanes include correctness/regression risk,
  maintainability/API shape, UX/product fit, security/privacy, and repo-specific
  instructions. Keep each lane scoped and read-only. Do not add a
  security/privacy lane by boilerplate when the reviewed surface and mission do
  not make it relevant.
- Before dispatch, declare a small lane ledger. Give every lane a stable key,
  provider, invariant/scope, target subset, and `required: true|false`. Do not
  retroactively make an omitted, failed, or inconvenient required lane optional.
  Every non-bypassed closeout must have at least one required independent lane
  from a different provider than the owning agent. Zero required cross-provider
  lanes terminates as `HUMAN_REVIEW_REQUIRED`, not vacuous `CLEAN`. The union of
  required lane target subsets must cover every frozen manifest member and
  closeout claim; uncovered targets also terminate as
  `HUMAN_REVIEW_REQUIRED`. Track which outputs arrived, which findings were
  accepted/rejected, and what validation remains.
- Preserve reviewer continuity. For every external or subagent lane that returns
  a blocking-now finding, record its session id or agent id. After addressing or
  materially rejecting that blocking finding, resume that same lane for a
  focused re-check before final synthesis. Fast-follow findings do not create a
  re-review obligation for the current checkpoint. If the original session
  cannot be resumed, brief one replacement in the same lane with the original
  finding, fix or rejection rationale, latest manifest, and validation; record
  the continuity break.
- Any body of durable work makes this gate applicable. A request that produces
  no durable artifact, decision, external mutation, or state change may report
  the gate as not applicable; that is not a bypass and not a `CLEAN` review.
- Use only these terminal states for an applicable gate:
  - `CLEAN`: every declared required lane and every lane that returned an
    accepted blocking-now finding reviewed the latest artifact revision for its
    complete frozen target subset and explicitly returned `CLEAN` or "no
    blocking findings." Documented fast follows may remain.
  - `HUMAN_REVIEW_REQUIRED`: a required lane is missing after the bounded
    fallback, a blocking-finding lane is missing its continuity verdict,
    required lane coverage does not span the full manifest and claims, an
    accepted blocking-now finding remains unresolved, or a reviewer maintains a
    source-backed blocking finding after one focused rebuttal. This state may be
    handed to the user, but the work is not ready to ship, close, or describe as
    clean.
  - `BYPASSED`: the user or human operator explicitly waives the gate; an
    upstream manager acts under a current capability envelope that explicitly
    grants critique-bypass authority; or a documented urgent-hotfix policy
    explicitly grants that authority to the current owner. A role title,
    confidence, deadline, provider cost, or self-classified low risk is not
    authority. Record the authorizer or policy and missing evidence; never call
    this `CLEAN`.
- A timeout, stale pre-fix verdict, missing reviewer, or unresolved accepted
  blocking-now finding cannot clear the gate. Do not pressure a reviewer into approval. After
  one focused rebuttal of a rejected finding, unchanged dissent terminates as
  `HUMAN_REVIEW_REQUIRED` with both positions recorded.
- Review reports, adjudication, fixes, and re-checks produced inside an active
  critique are rounds of that same workflow, not new durable targets that launch
  nested critique. A materially new target created after the workflow closes
  starts a new gate.
- Bound the review. Stop once the meaningful risks are addressed and the work
  honors the frozen mission. Do not keep mining for improvements after the
  checkpoint is safe to ship.

## Build the Review Context

Before dispatching reviewers, derive a small context packet from the target
instead of sending broad repository context:

1. List the changed files or the exact artifacts under review and classify the
   changed surface (for example CLI routing, persistence, UI, or workflow
   behavior).
2. Read the nearest applicable repo guidance for those files, including
   `AGENTS.md`, `CLAUDE.md`, and any user-named skills. Extract only rules that
   govern the changed surface; do not attach guidance for untouched areas.
3. Check whether the repo declares a scaffold, generator, or canonical example
   for that surface. Record the files and registrations it expects rather than
   assuming a generic checklist.
4. Record the repo's actual validation tiers: what the pre-commit hook runs,
   which focused tests exercise the natural boundary, and which required checks
   still rely on CI or a live environment.
5. Include the user's scope and explicit constraints verbatim enough that every
   lane can distinguish a defect from an unwanted expansion.
6. Require each finding to declare `scope disposition: blocking now | fast
   follow | rejected`, while making clear that this is a recommendation for the
   main agent to adjudicate, not a decision.

Give each reviewer the target diff/artifact plus this packet and its focused
lane. If the applicable contract cannot be established from source, investigate
that gap in the main thread instead of asking reviewers to invent one.

## Finding Admission Gate

The main agent must apply this gate after receiving reviewer output. Admit a
finding only when all four conditions are satisfied:

1. **Reachable trigger:** a current code path, input, configuration, or workflow
   can produce the behavior. Hypothetical future scale or imagined consumers do
   not qualify.
2. **Exact evidence:** cite the responsible `file:line` in reviewed or directly
   touched code. For non-code targets, cite the exact transcript, runtime
   artifact, or documented contract that proves the behavior.
3. **Concrete impact:** explain the correctness, safety, or Agent Experience
   failure caused by the trigger. Preference-only cleanup and speculative
   performance advice do not qualify.
4. **In-scope fix:** identify a bounded correction that fits the user's request
   and the target's existing design. If the impact is real but the fix requires
   a scope decision, put it under residual risk or user judgment instead of
   presenting it as an actionable finding.

Silently drop suggestions that fail the gate. Mention a rejected suggestion
only when its rejection changes scope, resolves a reviewer disagreement, or
requires user judgment; critique output is not an audit log of every idea an
outside reviewer produced.

## Readiness Claims

Do not call work ready when an applicable repo- or user-required validation did
not complete. A focused alternative may substitute only when it proves the same
changed boundary. Otherwise name the exact unverified boundary and recommend a
PR/CI path when that is the available way to obtain proof. Passing unrelated
tests never converts an incomplete required gate into qualified success.

## Advisor And Reviewer Fast Path

Before assigning any advisory or review lane, define:

- one decision to make or invariant to test;
- the exact artifacts, files, or diff hunks to inspect;
- allowed operations, often with commands and repo-wide search forbidden;
- a concise output contract with an explicit verdict; and
- a total budget plus a maximum idle interval.

A timeout or response without the requested verdict is Agent Experience
friction even when the execution surface reports the failure accurately. It is
not approval, and missing review cannot clear the critique.

After the first no-verdict outcome, transform the contract before rerouting:
keep the frozen target subset intact while narrowing the question or supplied
context, restricting allowed operations, and shortening the output. A lane may
use smaller probes only when their aggregate still covers its complete original
target subset and invariant. After a second no-verdict outcome, compare another
reviewer with direct review and take the work back when direct review is faster.
Taking it back means the lead performs direct review for diagnosis, records
`HUMAN_REVIEW_REQUIRED`, and asks an authority recognized by the canonical
`BYPASSED` rule whether to fix, replace the lane, or authorize the bypass. Never
present direct review as independent approval or as satisfying a required
cross-provider critique.

## Repeated Slice Requests

Do not interpret "critique every slice" as automatic permission to run the full
multi-agent, cross-provider workflow after each internal slice. Explain that
repeated passes multiply provider startup, context reconstruction,
adjudication, fix, and re-review cost and can delay the coherent integration
that reviewers actually need to assess.

Unless the user explicitly confirms they want repeated cross-provider critique
despite that cost, give each settled slice focused tests, main-agent review, and
targeted continuity rechecks for concrete findings, then run one formal critique
against the integrated milestone. If the user explicitly confirms per-slice
formal critique, keep each pass bounded to a settled artifact and avoid asking
multiple reviewers to rediscover the same cross-cutting issue.

## If You Are Codex

Use Claude plus focused same-provider lanes when they are available:

1. Load and follow `~/.agents/skills/claude/SKILL.md` to ask
   Claude for an independent critique. Give Claude a self-contained prompt with:
   - the user goal,
   - the files or diff being reviewed,
   - what has already been checked,
   - the repo principles that matter,
   - the requested output shape: actionable findings, non-findings, and risks.
2. Spawn one or more focused Codex subagents when the environment supports it.
   Good lanes are:
   - correctness and regressions,
   - maintainability/API shape,
   - security/privacy/data-boundary review,
   - repo-specific principles and Agent Experience.
3. Keep every reviewer lane independent and read-only. The owning agent fixes
   accepted findings within its existing authority. Give each lane a concrete
   scope and expected output; do not ask every lane the same vague "thoughts?"
   prompt.
4. Run these lanes in parallel when the tool environment allows it. If a lane
   cannot run in parallel, run it as soon as possible without blocking on
   unrelated review work.
5. Compare the outputs. Keep findings that are real, source-backed, and aligned
   with the repo's review philosophy. Push back on low-signal nitpicks.
6. If you address or reject a Claude finding, use the same Claude session
   (`--resume <session_id>` from the Claude wrapper output) for the follow-up
   re-check. If a Codex subagent raised the finding, return the addressing
   summary to that same subagent when the environment supports it.

Use `~/.agents/skills/codex-review/SKILL.md` only when the user
explicitly invokes `/codex-review` or asks for that legacy single-Codex review
flow. Do not make it the default critique lane.

Do not blindly paste long advisory output. Summarize the useful parts, call out
disagreements, and recommend the next action.

## If You Are Claude

Use Codex plus focused same-provider lanes when they are available:

1. Load and follow `~/.agents/skills/consult/SKILL.md` when
   available, or `~/.agents/skills/codex/SKILL.md` as the
   provider-specific backend, to ask Codex for a deeper source-backed critique.
   Package the question as a brief, not a vague "thoughts?" prompt.
2. Run Claude subagents for focused review lanes when the environment supports
   them. Good lanes are:
   - correctness and regressions,
   - code quality and maintainability,
   - repo-specific principles and Agent Experience.
3. Run independent lanes in parallel when possible and keep every reviewer lane
   read-only. The owning agent fixes accepted findings within its existing
   authority.
4. Compare Codex and subagent outputs against the code and repo guidance. Keep
   only findings with real current impact.
5. If you address or reject a Codex finding, resume the same `consult` /
   `codex` skill session for the follow-up re-check. If a Claude subagent raised
   the finding, return the addressing summary to that same subagent when the
   environment supports it.

If subagents are not available, say so and proceed with `consult` / `codex`
plus your own review.

## Output Shape

Return a concise synthesis:

- Target manifest and required lane ledger, including reviewer/session ids.
- Blocking-now findings, grouped by priority. Each finding must state its
  reachable trigger, exact evidence, concrete impact, and bounded fix.
- Fast follows that were ticketed without changing the current checkpoint.
- Findings rejected only when the rejection changes scope, resolves a reviewer
  disagreement, or needs user judgment, with a one-line rationale.
- Residual risks or tests still worth running.
- Terminal state: `CLEAN`, `HUMAN_REVIEW_REQUIRED`, or `BYPASSED`.
- Recommended next move.

If there are no real findings, say that plainly.
