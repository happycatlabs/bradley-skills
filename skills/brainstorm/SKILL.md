---
name: brainstorm
description: Cross-agent brainstorming and idea critique for early-stage decisions, architecture options, product/workflow design, debugging hypotheses, implementation strategies, or "what are we missing?" questions. Use when the user asks to brainstorm, workshop, explore options, stress-test an idea before implementation, compare possible approaches, or get Claude/Codex perspectives on a hypothetical plan. Prefer `critique` for reviewing existing diffs, completed work, push readiness, or concrete artifacts.
---

# Brainstorm

Use this skill to widen the option space, then narrow it responsibly. The mode is divergent first, convergent second: generate plausible approaches, pressure-test them, identify what would change the recommendation, and end with a practical next move.

This is not `critique`. `critique` reviews existing work or artifacts and should be source-backed. `brainstorm` can reason about hypothetical ideas, but it must label assumptions and avoid laundering speculation into fact.

## Workflow

1. Frame the problem:
   - Restate the decision, goal, constraints, and success criteria in one compact paragraph.
   - Separate known facts from assumptions.
   - If the idea depends on code, docs, or another agent/session, inspect only enough source material to make the brainstorm grounded.

2. Choose lanes:
   - Small or low-stakes question: use the other-provider advisory lane plus your own reasoning.
   - Medium question: add one same-provider subagent for an independent option-generation or contrarian lane.
   - Large or ambiguous question: use two to four lanes with distinct jobs. Do not spawn duplicate "thoughts?" lanes.

3. Run cross-agent input:
   - If you are Codex, load and follow `~/.agents/skills/claude/SKILL.md` for the other-provider lane.
   - If you are Claude, load and follow `~/.agents/skills/consult/SKILL.md` or `~/.agents/skills/codex/SKILL.md` for the Codex lane.
   - Give outside agents a self-contained prompt: user goal, relevant context, current candidate ideas, constraints, and the exact output shape wanted.

4. Run same-provider subagents when useful and available:
   - Treat an explicit `brainstorm` invocation as a request for agent-assisted ideation, but still keep fan-out proportional to the question.
   - If you are Codex and a subagent tool such as `spawn_agent` is available, use it for same-provider lanes.
   - If you are Claude and Claude subagents are available, use them for same-provider lanes.
   - Use focused roles such as `option generator`, `contrarian`, `implementation planner`, `risk finder`, `agent-experience reviewer`, or `product/UX lens`.
   - Keep each lane read-only unless the user explicitly asked for implementation.
   - Make lanes independent: one lane should not just re-answer another lane's prompt.

5. Synthesize:
   - Cluster ideas instead of listing every suggestion.
   - Name the strongest option and why it wins.
   - Name the best rejected option and why it loses.
   - Call out assumptions, unknowns, and the smallest experiment or check that would change the recommendation.

6. Re-check addressed feedback:
   - Record session ids or agent ids for outside and same-provider lanes that return concrete concerns.
   - If you later change the plan, prototype, or implementation in response to a lane's concern, resume that same lane when possible.
   - Present the original concern, the updated idea or change, and why rejected concerns were not adopted. Ask whether the concern is resolved or whether the updated plan still has a sharper failure mode.
   - Do not substitute a new agent for the one that raised the concern unless continuity is unavailable; say so if that happens.

## Prompt Patterns

Other-provider prompt:

```text
We are brainstorming an early-stage decision, not reviewing a final diff.

Goal:
<what the user wants>

Context:
<facts, constraints, relevant files/session notes if any>

Current ideas:
<optional candidates already on the table>

Please propose 2-4 viable approaches, pressure-test them, and recommend a default. Label assumptions. Do not modify files.
```

Same-provider subagent prompts:

```text
Generate options only. Given this goal and constraints, propose distinct approaches the main agent may be missing. Do not choose a winner unless one option clearly dominates.
```

```text
Be the contrarian. Stress-test the current preferred idea, identify failure modes, and say what evidence would change your mind. Do not modify files.
```

```text
Plan the smallest useful experiment. Given these candidate ideas, propose the cheapest check or prototype that would reduce uncertainty. Do not modify files.
```

## Output Shape

Return a concise synthesis:

- Recommended direction.
- Why it beats the main alternatives.
- Best alternative to keep in reserve.
- Risks, assumptions, and unknowns.
- Next concrete step or experiment.

If the brainstorm reveals that the user is really asking for review of existing work, switch to `critique` and say why.
