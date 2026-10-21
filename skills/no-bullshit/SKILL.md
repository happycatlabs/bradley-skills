---
name: no-bullshit
description: Review plans, product flows, APIs, code, and explanations for needless complexity, confusing language, wasted effort, and unsupported claims. Use when making design tradeoffs, simplifying work, reviewing usability, or explicitly asked for /no-bullshit. API naming is one application, not the whole skill.
---

# No bullshit

Choose the simplest complete solution that serves the user's actual goal. Make
it understandable, make it work, and prove the parts you claim work. Apply this
judgment during ordinary work; do not add a mandatory audit phase to every task.

## Start with the actual job

- State what must become true for the user. A plan, ticket, PR, monitor, or
  workaround can support that result; it cannot silently replace it.
- Show the normal user or caller path before building it. If it needs insider
  knowledge, repeated setup, or an explanation for an obvious name, simplify it.
- Use the user's product language and established conventions. Do not invent
  concepts, terminology, or a bigger system to make a small task feel important.

## Make the experience obvious

- Use plain words that say what an action does. Keep internal mechanics inside
  the implementation. Explain a necessary technical term when it helps a real
  decision; remove it when an ordinary word is equally precise.
- Give the common case a short, functional path with sensible defaults. Keep
  advanced controls discoverable without making them everyone's setup chore.
- Reuse context the caller already supplied when it is safe and expected. Show
  the resolved target and preserve explicit targeting for consequential actions.
- Write useful copy and documentation: real examples, actual requirements,
  actionable errors, and honest availability. Remove filler and placeholders.

## Make complexity earn its place

- Prefer direct code and existing mechanisms. Add an abstraction, dependency,
  service, setting, or workflow only when it solves a demonstrated current need.
- Remove duplicated state, speculative extension points, and pass-through layers
  that make ordinary behavior harder to follow. Do not chase fewer lines at the
  expense of clear responsibilities or correctness.
- Keep necessary complexity: authorization, privacy, data integrity, concurrency,
  recovery, and real compatibility requirements. Simplicity is not a reason to
  weaken them or pretend the problem is smaller than it is.

## Respect time and credits

- Take routine steps already authorized by the task. Ask for a decision only
  when a real missing choice or authority boundary prevents safe progress.
- Use the cheapest capable approach. Delegate only when the independent work
  saves time or materially lowers risk; do not create ceremonial panels.
- Run required checks and targeted proof. Repeat a review or broad suite only
  after relevant changes, failures, or unresolved concerns justify it.
- Keep the fix bounded. Classify nearby improvements separately instead of
  turning a small correction into a redesign or another approval workflow.

## Be honest about results

- Check available first-party evidence before answering a factual question.
  Separate what you observed from what you inferred or have not verified.
- Match proof to the claim. Source, tests, publication, deployment, transport
  acceptance, and the requested user outcome establish different facts.
- Lead with the result, or the concrete unmet requirement. Give the evidence
  and remaining limitation plainly. Do not hide an incomplete result behind
  progress language, confident copy, or an unrelated success.

## Public APIs are one application

- Default to conventional verbs such as create, get, list, update, and delete.
  Use clear domain actions such as send, invite, accept, or pause when those
  describe the operation better. Follow established protocol terms when needed.
- A command that creates an app should be named create. Safe retry behavior is
  part of its contract; it does not require the caller to learn an internal verb.
- Prefer typed methods, meaningful parameters, and discoverable commands over
  generic call(operationString, mysteryArguments) interfaces for normal use.
- Keep authentication, target selection, pagination, errors, side effects, and
  asynchronous completion consistent and explicit where they matter.
- Do not use a word blacklist. Internal ensure helpers, genuine reconciliation,
  documented protocol actions, and existing compatibility aliases are not bugs
  merely because a different public operation used a confusing name.

## When reviewing existing work

Read the real caller path and authoritative contract. Identify the concrete
cost: a failed workflow, unnecessary decision, surprise, repeated work, confusing
contract, or claim without evidence. Do not invent findings to fill a quota.

For each material issue, give the evidence, caller impact, and smallest useful
change. Distinguish an ordinary compatible repair from a product decision or
breaking migration. An audit does not itself authorize production mutation or
mass renaming. Do not flag documented custom actions merely for differing from
one preferred style. Report coverage and gaps; do not claim an exhaustive audit
from a keyword search or a small sample.
