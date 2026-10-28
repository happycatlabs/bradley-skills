---
name: api-design
description: Design or review public APIs, SDKs, CLIs, and MCP tools for clear caller intent, usable responses, safe state changes, and agent ergonomics. Use for new contracts, naming decisions, and confusing existing flows; skip for mechanical implementation of an already settled contract.
---

# API design

Design the operation the caller needs, not the internal record or queue step that happens to implement it. Start with one ordinary caller flow in the API, CLI, and SDK surfaces that exist for the product. Consult the current product decision page, ticket, source contract, and release state when available; label proposed behavior separately from shipped behavior.

## Find the right primitives

- Name the caller's action and the resource it acts on. Check each name against a plausible wrong reading: Does `create` sound like submitting a verdict? Does `run` imply a result when the call only queues work? Does `accept` mean internal selection, merge, or release? Resolve the ambiguity with the operation name, inputs, response, and docs together.
- Choose a small set of stable nouns and verbs. Reuse an operation across targets when the behavior is truly the same; keep product-specific actions with their owning resource. Do not publish two ways to do one action merely because an SDK shortcut is convenient.
- Keep returned data serializable and useful through HTTP, CLI JSON, MCP, and SDK. If an object method would disappear after serialization or hide a network side effect, compare it with an explicit client operation before adopting it.
- Model source/version identity, state, result, and authority separately. A queued task, unavailable provider, failed check, review finding, approval decision, accepted change, merge, deployment, and release are different facts.

## Make an agent's next step obvious

The normal read should answer: what is this exact object, what is known now, what blocks the requested action, and what can the caller do next? Include stable IDs and reason codes, plain messages, and direct links or typed read arguments for deeper evidence. A zero or empty list must not hide whether nothing ran, everything passed, or results were unavailable.

For asynchronous work, return a durable operation ID and actual state immediately. Provide a read for progress and outcome; make waiting an optional CLI convenience. Define retry behavior and stale-source rejection. Mutating calls must recheck current authority; a prior status read is not permission.

Keep the common response bounded. Put summary and relevant blockers on the parent object; provide direct detail, pagination, structured failures, and privacy-safe logs where needed. Choose defaults by measuring response size, latency, tool calls, and agent success on representative cases. Do not expose an implementation cap as a permanent public contract without a reason.

## Pressure-test before settling a novel shape

Sketch two or three materially different caller paths. For each, show one success response and one failure, then ask a fresh reviewer which reasonable misreading or wrong action the contract permits. Give that reviewer exact current docs, tickets, source revision, settled user decisions, and open assumptions; ask it to challenge those assumptions. Verify its claims against source and user context before adopting them. Compare relevant primary APIs for useful patterns, without copying their nouns or complexity by default.

Finish with one recommended public shape, the strongest rejected alternative, compatibility/migration implications, and the cheapest real caller test that could change the choice. Once the contract is settled, update executable examples, docs, and behavioral checks alongside implementation. Keep source, package release, deployment, and live consumer proof distinct.
