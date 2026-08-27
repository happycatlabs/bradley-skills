---
name: composition
description: How to start a new UI with judgment. Hierarchy, density, system, restraint, state coverage. The phase before polish.
type: reference
---

# Composition

Polish is well-tooled. The layer underneath — *what goes on the screen, in what order, at what density, with what reduced* — is where AI-generated UI fails. This file is the operating manual for that layer.

The frame to carry into every UI task: **quality is the deliberate act of caring** in a world where the default is to outsource caring. Karri Saarinen, Linear: *"with each prompt, we're trying to outsource not just labor, but the craft itself."* The skill is what you refuse to outsource.

## 1. The pre-code interview

Before you write a single line of layout code, answer these in plain text. Skipping this is the single biggest cause of generic output.

1. **What is this surface for?** One sentence. The job. If you can't write it in one sentence, the design will sprawl.
2. **Who is using it, and what state are they in?** Rushed? Anxious? Comparing? Browsing? The emotional context determines density, copy, and where the eye should land. Saarinen's Rule 7: *"You can only create a great product if you design for someone in particular."* AI defaults to designing for everyone, which produces nothing.
3. **Primary, secondary, tertiary.** What's the one action or piece of information this surface exists to serve? What supports it? What's reference-only? Cut at least one thing you'd otherwise include.
4. **Where does the eye land first?** Pick the focal point explicitly. Every other element should be calibrated to recede *from* that focal point. AI UIs are flat in gravity because nothing was chosen as the anchor.
5. **Tool surface or content surface?** Tools (Linear, Notion, dashboards) reward density. Content surfaces (marketing, docs, articles) reward air. They have *different rules* — one of the most common AI failures is applying marketing-airy rules to a tool, or dashboard-dense rules to a hero.

If the brief is vague, write the surface's job statement yourself and confirm with the user before laying out anything.

## 2. System over components

Pick a **small, opinionated system** before reaching for any component. The system is what gives a screen visual coherence; components are interchangeable.

- **Type scale**: 4–6 sizes maximum. Display, title, body, caption, plus maybe one variant. Stick to them. Don't reach for `text-3xl` ad-hoc.
- **Weight palette**: 2–3 weights maximum. Most products need only regular and semibold. Adding a third weight is a real decision.
- **Color roles, not raw colors**: foreground, muted-foreground, background, surface, accent, destructive. Every color you use in a UI should be assignable to a role. If it's not, you're decorating.
- **Spacing scale**: a real scale (4 / 8 / 12 / 16 / 24 / 32 / 48 / 64), with rules for which gap signals which relationship. Uniform `gap-4` everywhere is the AI default and it kills rhythm.
- **One radius**, maybe two. Components share a radius; modals/sheets may use a larger one if the design language calls for it. `rounded-2xl` on every element is a fingerprint.
- **A reference product whose vibe matches the brief.** Anchor to something concrete — *"Bloomberg-density data table,"* *"Linear-style focused list,"* *"Stripe Docs-style code-first marketing"* — not adjectives like "clean" or "modern." Vague references collapse to the training mean.
- **Steal modules, don't invent a personality.** Taste is a Lego set of real products: one density from Linear, one list behavior from Raycast, one sheet from Apple. Copy the module, then make it coherent. Do not generate a unique "system" from adjectives, and do not paste a shadcn/Base UI gallery into the brief and call it composition.

Saarinen's Rule 6: *opinionated by default, flexible underneath.* Make decisions; don't expose tokens.

## 3. Hierarchy through reduction

Most things on a screen should recede. Exactly one thing should dominate. AI-generated UIs are evenly weighted because the model has no model of *attention budget*.

- **Differentiate roles across at least two axes** — not just size. Heading and label that share a weight will compete; vary by case + tracking + color.
- **The squint test**: blur your eyes (or imagine doing it). What stands out? If the answer isn't the focal point you chose in §1.4, the hierarchy is wrong.
- **The 3-second test**: in three seconds of glance, can a user tell where they are, what they can do, and what to do first? If any answer is "no," reduce.
- **Reduce scope before reducing quality** (Saarinen, Rule 8). If asked to fit twelve items on one surface, propose cutting before cramming.

## 4. Grouping with proximity, not boxes

Cards-by-default is the lazy way to group. Most "cards" should not be cards.

- **Proximity first**: related elements touch, unrelated elements have air. If proximity does the work, no border or background is needed.
- **Borders and surfaces are a last resort**, used when proximity isn't enough — cross-cutting groups, persistent containers, elevated surfaces. Reaching for `border + rounded + shadow + p-6` on every group is the AI default.
- **Container soup is a smell.** If you have nested wrappers each with padding and a background, you're hiding the structure under chrome. Flatten until the structure is legible from spacing alone.

## 5. Density as a deliberate choice

Reframe from Matt Ström-Awn: **density = value / (time × space)**. Not "how packed" — how *productive* per unit of screen and user time. Bloomberg terminals, Craigslist, McMaster-Carr are dense because density is the right answer for those users.

- **Tools**: prefer dense. Tables beat card grids for repeating structured data. Inline metadata beats separate label rows. Aim to surface more without scroll.
- **Content surfaces**: prefer air, but earned air. Generous whitespace is a quality signal; uniform `space-y-8` everywhere is the AI default.
- **Don't pad an enterprise UI with hero-section whitespace.** That mismatch is the single most common AI density failure.
- **Resolve "simple" as "no unjustified element," not "fewer elements."** Linear and Raycast both ship denser UIs than typical SaaS while preaching simplicity. The reconciliation is Tufte's data-ink ratio: *every bit of ink requires reason.*

## 6. Real content, real numbers, real lengths

Lay out with real strings. Always. Layout decisions made on placeholder content fall apart on real data.

- **Use the longest realistic string** for any field, not the average one. Names that wrap, prices in different currencies, timestamps in different time zones, error messages with full sentences.
- **Use real numbers** with `font-variant-numeric: tabular-nums`. Mixed-width digits in a column scream amateur.
- **Cover the cardinality range**: what does this look like at 0 items, 1 item, 5, 50, 500? Each one is a real layout, not a "TODO."
- **Never use Lorem ipsum.** Write the actual copy, even rough. Copy decisions and layout decisions are the same decision.

## 7. State coverage from day one

Empty, loading, error, partial — designed *with* the happy path, not bolted on. The single most reliable AI tell is "happy path only."

- **Empty isn't "No data."** Empty is the surface's first impression for a new user. Design it as onboarding, default content, an example, or an explicit invitation. *"Tap + to add your first image"* is fine; *"No items yet"* on a blank screen is not.
- **Loading**: skeletons that preserve the shape of the populated state, not centered spinners. Add the show-delay (150–300ms) and minimum-visible (300–500ms) gates from `animations.md` so spinners don't blink.
- **Error**: tell the user what to do next, not what went wrong. *"Couldn't load. Try again."* with a button beats *"Error: ECONNREFUSED."*
- **Partial / streaming / stale**: design what the surface looks like when half the data is in, when the connection is degraded, when the cache is stale. Modern UIs spend more time partial than complete.

## 8. Meaning, not chrome

These are composition decisions, not polish:

- **One accent per view.** Headings stay neutral. Brand color is for links and actions. A second accent is a real decision, not decoration.
- **Never communicate status with color alone.** Pair it with a label or icon.
- **Visible labels.** Placeholder is not a label. Errors sit next to the field they belong to.
- **Sentence case for UI chrome.** `Save chat`, not `Save Chat` or `SAVE CHAT`. Reserve uppercase for tiny eyebrows that already have tracking.
- **Empty states get one action**, not a paragraph. Same as §7 — the action *is* the empty state.
- **Reserve space.** Images and media need `aspect-ratio` (or an equivalent fixed slot) so neighbors don't jump on load.

## 9. Editorial moves

Symmetric three-column grids and centered max-width heroes are the AI default precisely because they're the lowest-loss layout. Break the symmetry deliberately when the content rewards it.

- **Asymmetric splits**: 2/3 + 1/3, varied row heights, content that breaks out of the grid. Use when one element should dominate.
- **Editorial layouts** for content surfaces: full-bleed, captions in the margin, pull quotes, tabular sections inserted into prose.
- **Single-column annotated screenshot** beats *"three feature cards with icon + heading + paragraph"* for product marketing. Show the product, label what matters.
- **Density inversion**: a dashboard hero can be *less* dense than the rows below it (one big number, contextual delta) — varying density is itself hierarchy.

## 10. The handoff

When the composition is right:
- Run the [layout-reading.md](layout-reading.md) protocol mentally — does the structure render the way you intended?
- Run the [ai-slop.md](ai-slop.md) audit — are any of the named fingerprints showing up?
- Then hand to the polish layer (the numbered principles in `SKILL.md`) for radius, easing, hit areas, font smoothing, etc.

Order matters. Polishing a generic structure produces a polished generic UI.

## Sources

- Karri Saarinen, *"Why is quality so rare?"* — https://linear.app/now/why-is-quality-so-rare
- Karri Saarinen, *"10 rules for crafting products that stand out"* (Config 2025) — https://www.figma.com/blog/karri-saarinens-10-rules-for-crafting-products-that-stand-out/
- Matt Ström-Awn, *"UI Density"* — https://matthewstrom.com/writing/ui-density/
- Rauno Freiberg, *"Invisible Details of Interaction Design"* — https://rauno.me/craft/interaction-design
- Edward Tufte, *The Visual Display of Quantitative Information* — data-ink ratio.
- Collect real product modules as a Lego set rather than inventing a system from adjectives.
