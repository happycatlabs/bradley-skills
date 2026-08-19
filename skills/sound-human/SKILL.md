---
name: sound-human
description: Rewrite or review human-facing prose so it reads like a thoughtful person wrote it. Use for internal documentation, onboarding guides, technical explanations, knowledge-base pages, tickets, pull request descriptions, handoffs, status updates, and other writing that feels robotic, jargon-heavy, over-structured, ambiguous, or obviously AI-generated. Preserve the writer's meaning and tone while improving first-read comprehension, specificity, rhythm, and natural voice.
---

# Sound Human

Make the writing easy to understand on the first read. Human voice comes from clear judgment, concrete details, and natural rhythm, not fake slang or manufactured personality.

## Rewrite workflow

1. Identify the audience and what they need to understand or do.
2. Preserve the facts, decisions, constraints, links, and intended tone.
3. Preserve any requested format, template, or useful organizational structure.
4. Rewrite around concrete actors and actions.
5. Define unfamiliar terms when they first appear, or avoid them when plain words work.
6. Remove AI tells and unnecessary structure.
7. Read the result as a newcomer and fix every remaining ambiguity.
8. When feedback reveals a repeated writing problem, scan the rest of the piece for the same problem unless the user explicitly limited the edit.

Return the rewritten prose without narrating the editing process unless the user asks for an explanation.

Use the shape that fits the writing. Preserve both meaning and any structure that helps the reader or satisfies a requested format. Do not invent sections, lists, or a new outline when the piece does not need them. Reorganize only when the user asks for it or the existing structure materially hurts comprehension.

## Review mode

When asked to review rather than rewrite:

- Quote the unclear or unnatural wording.
- Explain briefly why it is hard to follow or sounds robotic.
- Suggest a clearer direction without rewriting the whole piece unless asked.
- Group repeated writing problems instead of listing every instance.
- Do not invent findings for prose that is already clear.
- Stay focused on the writing. Do not turn the pass into fact-checking, technical review, product analysis, or requirements validation.

## Choose the level of edit

- Treat the user's requested format, template, section headings, and ordering as constraints unless invited to change them.
- Default to line editing within useful existing structure. Sounding human and preserving the writer's intent matter more than producing an idealized outline.
- Restructure when the user asks, when the source has no usable organization, or when repetition and poor ordering materially hide the point. Make the smallest structural change that solves the problem.
- If restructuring is warranted, put the mental model before unfamiliar systems or code terms and move volatile rollout notes below durable behavior.
- Keep a table, diagram, callout, or section when the user chose it, a template requires it, or it makes the rendered document easier to use. Remove it only when it is decorative or duplicative.
- Default to an output no longer than the source. Expand only to define a necessary term or add context the user requested. If the draft grows, cut repetition before returning it.
- Preserve status qualifications without preserving shouting, awkward labels, or source phrasing. "Work has not started" carries the same fact as "CONFIRMED NOT STARTED."
- Do not settle for synonym replacement when sentences are genuinely unclear. Fix the specific sentence, paragraph, or section causing the problem.

## First-read clarity

- Introduce a component by saying what it is and what it does. A name alone is not an explanation.
- Name who acts, what happens, and where it happens. Prefer "The billing service creates the invoice" to "invoice creation is handled downstream."
- Replace vague references such as "it," "this," "the path," and "the system" when more than one meaning is possible.
- Resolve ambiguity from facts the user or source provides. If the missing actor, state, or behavior is unknown, preserve that uncertainty or ask; do not guess to make the prose sound complete.
- If a sentence sounds polished but is difficult to restate plainly, rewrite it using concrete actions, facts, or consequences.
- Separate stages that people commonly collapse. "Requested," "queued," "accepted by the provider," and "delivered" are not all "sent."
- Put code terms after the plain-language explanation. Define a term once, then use it consistently.
- Spell out or explain unfamiliar acronyms at first use, including acronyms inside headings, diagrams, and link labels.
- Link code after the claim it supports. Do not make the link carry the explanation.
- Layer detail. Start with the main flow, then move specialized behavior, rollout notes, code maps, and debugging details into later sections or focused pages.
- Keep mutable status notes dated and separate from durable system behavior.

## Natural voice

- Preserve the writer's level of formality. Do not make professional writing chatty for its own sake.
- Use contractions when they fit.
- Vary sentence length. Let a short sentence land when the point is simple.
- Prefer direct statements over ceremonial transitions and throat-clearing.
- Be candid when the source is candid. Keep useful phrases such as "not ideal" or "we still need to decide" when they reflect real judgment.
- Repeat the same noun when synonym changes would make the reader translate.
- Prefer ordinary words such as "use," "build," "send," "check," and "change."
- Do not invent anecdotes, emotions, jokes, opinions, or personal experience.

## Remove AI tells

Cut or rewrite:

- inflated claims such as "pivotal," "robust," "seamless," and "comprehensive";
- filler such as "it is important to note," "in order to," and "this ensures that";
- abstract verbs such as "leverages," "facilitates," "orchestrates," "hydrates," and "plumbs" when a concrete verb works;
- forced contrast patterns such as "not just X, but Y";
- fake precision built from invented umbrella terms;
- repetitive summaries that restate the heading or previous paragraph;
- em-dash-heavy sentences, bold soup, decorative callouts, and tables used only to make prose look structured;
- perfectly symmetrical lists when the subject does not naturally have that shape;
- conclusions that say nothing beyond "this improves the experience."

Formatting should help the rendered document. Use a table for a real comparison or mapping. Use a diagram only when it is easier to read than a sentence and renders cleanly in the destination. For process diagrams in narrow document layouts, prefer a vertical flow over a long horizontal line. Stack the main sequence and branch only where outcomes diverge.

## Ambiguity pass

For each paragraph, ask:

- Who is acting?
- What exactly happens?
- Where does it happen?
- Would a new reader understand every necessary term?
- Does "success," "complete," "current," or "sent" name a precise state?
- Does any pronoun have more than one possible referent?
- Is a temporary rollout detail presented like a permanent rule?

Rewrite until every answer is obvious from the text itself.

## Examples

Before:

> The system orchestrates the downstream notification flow and ensures successful delivery.

After:

> The notification worker queues the message. The template service builds it, and the email provider attempts delivery. A successful queue request does not prove that the recipient received it.

Before:

> Product code is propagated through the flow.

After:

> The vendor returns a `productCode` with the offer. The API saves it and sends the same product type to the eligibility service.

Before:

> This change enhances reliability by leveraging source-state verification.

After:

> After the command writes the record, it reads the database to verify the change.

## Respect local conventions

Follow any product, brand, repository, or artifact-specific guidance supplied with the task. Those sources determine terminology, approved copy, and required structure. This skill determines clarity, ambiguity, and natural voice.
