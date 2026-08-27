---
name: layout-reading
description: A syntax-agnostic protocol for mentally rendering UI from layout code before generating it. Forces explicit spatial reasoning instead of pattern-matching to training data. Run this on your own output before considering it done.
type: reference
---

# Layout reading: render it in your head first

Most AI UI failures are pre-code: the model never visualized the result before producing it, so the layout is ungrounded — orphaned flex children, miscentered stacks, missing cross-axis alignment, no focal point. The published research is consistent on the fix: **forcing an explicit intermediate representation before code reduces ungrounded layout failures.**

> ScreenCoder's planning agent emits a hierarchical layout tree before any code is written; this beats single-shot generation. *(Wang et al., 2025, https://arxiv.org/abs/2507.22827)*
>
> Cartesian-JSON layouts (x, y, w, h) outperform natural-language descriptions for spatial reasoning tasks. *(LaySPA, https://arxiv.org/abs/2509.16891)*
>
> Models can reason over 2D character grids; an ASCII sketch as scratchpad measurably improves spatial-reasoning task accuracy. *(ASCIIBench, https://arxiv.org/abs/2512.04125)*

The plan-then-generate finding is well-established. What's *not* yet published — and what this file tries to do — is a single-prompt, framework-agnostic mental rendering protocol that works in one Claude turn without tools.

## When to run this

Run this protocol mentally:

- **Before** writing the code for any non-trivial layout (more than 3 sibling elements at any level, any z-stacking, any responsive breakpoints).
- **After** writing the code, as a self-audit, before considering the output done.
- **When reviewing** layout code from another source (yours, the user's, an existing component) and the rendered result feels wrong.

Skip it for trivial cases (a single button, a one-line label).

## The vocabulary

Use these five primitives. They cover ~95% of UI layout across React, React Native, SwiftUI, Flutter, Jetpack Compose, and plain CSS. Use them *internally* even if the target framework spells them differently.

| Primitive | What it does | Maps to |
|---|---|---|
| **Stack** | 1D arrangement of children along an axis | `flex`, `HStack` / `VStack`, `Row` / `Column`, `Stack`, `<div style="display:flex">` |
| **Frame** | A bounded container: pads, sizes, optionally clips and backgrounds. Holds at most one child layout. | `div`, `View`, `Container`, `Box`, `frame()` |
| **Grid** | 2D allocation of children into rows × columns | `display:grid`, `LazyVGrid`, `GridView`, `Grid` |
| **Z-stack** | Children share the same coordinates, layered front-to-back | `position:absolute`, `ZStack`, `Stack` (Flutter) |
| **Spacer** | A flexible gap that consumes available space along the parent's axis | `ml-auto` / `flex-1`, `Spacer()`, `Expanded()` |

Every Stack and Frame has these properties. Name them explicitly when reading code.

| Property | Values | What it answers |
|---|---|---|
| **axis** (Stacks only) | `horizontal` \| `vertical` | Which way do children flow? |
| **distribution** (along axis) | `start` \| `end` \| `center` \| `between` \| `around` \| `evenly` | How is leftover main-axis space allocated? |
| **alignment** (across axis) | `start` \| `end` \| `center` \| `stretch` \| `baseline` | Where do children sit on the cross-axis? |
| **gap** | a value from the spacing scale | Distance between siblings |
| **sizing per dimension** | `fixed:N` \| `fit` (intrinsic) \| `fill` (parent's free space) \| `min:N` \| `max:N` | How does it want to size? |

## The protocol

Run these steps mentally — or write them out explicitly in a planning block before code. The research suggests the explicit version produces better output; the mental version is faster once practiced.

### Step 1 — Establish the bounding box

What is the viewport / parent / canvas this surface lives in? Width × height (or width × `auto`). Mobile portrait, tablet, desktop max-width? Edge-to-edge or insets? Without this, every "fill" decision below is meaningless.

### Step 2 — Walk the tree, naming primitives

Read the code top-down. At each level, name the primitive (Stack / Frame / Grid / Z-stack / Spacer) and its properties using the vocabulary above. Don't think in framework terms. `flex justify-between items-center` is *Stack, axis=horizontal, distribution=between, alignment=center.*

### Step 3 — Project to mental 2D

For each level, project the children onto a mental 2D rectangle. For Stacks: a row or column with the gaps and leftover space placed per `distribution`. For Grids: a 2D allocation. For Z-stacks: a layered diagram with explicit front-to-back order.

For non-trivial layouts, **drop into ASCII sketching**. A 12–24 character grid is enough. ASCII-as-scratchpad is the lowest-overhead way to surface alignment errors before they bake into code.

```
+----------------------------------+
|  [Avatar]  Title              >  |
|            Subtitle              |
+----------------------------------+
```

If you can't draw it, you can't render it; if you can't render it, the code is guessing.

### Step 4 — Track z-layers separately

Anything with `position:absolute`, `ZStack`, modal/popover/tooltip, sticky, fixed, or floating — list it on a separate plane. Note its anchor (which element it relates to in 2D space) and its trigger (what brings it on screen). Z-layer mistakes (popovers anchored to the wrong element, modals not over a backdrop) are invisible in linear code and obvious in a layered diagram.

### Step 5 — Compute gravity

Gravity is where weight lives in the 2D image. Weight = `size × saturation × density × surface contrast`. A large bold heading on a high-contrast surface has heavy gravity. A small muted timestamp has near-zero. Walk the rendered image and rank elements by gravity.

### Step 6 — Identify the focal point

The focal point is the element with the highest gravity *that you intended to be the focal point*. If those don't match — the heaviest element isn't the one that should dominate — the visual hierarchy is wrong. Adjust gravity (size, weight, color, or surrounding density) until they match.

### Step 7 — Smell tests

Apply these tests to your mental render. Each one names a specific failure mode AI-generated layouts fall into.

- **No focal point.** Every element has roughly equal gravity. The eye has nowhere to land. *Fix:* pick one element and amplify gravity (larger, bolder, more saturated, more isolated). Reduce gravity on the rest.
- **Flat hierarchy.** Heading, body, and label all read at the same visual weight. *Fix:* differentiate roles across at least two axes (size + weight, or weight + color, or case + tracking). See `typography.md`.
- **Ungrouped siblings.** A Stack with 5+ children at the same level with no internal grouping. The eye has to parse them linearly. *Fix:* group with proximity (varying `gap`), with sub-Stacks, or with a Frame. If proximity doesn't suffice, only then a border or surface.
- **Uniform density.** Every gap is the same value (`gap-4` everywhere). Spacing carries no information. *Fix:* use spacing as rhythm — tight where elements are related (4–8), generous where the structure breaks (16–32+). Same `space-y` everywhere = no rhythm.
- **Unbalanced gravity with no intent.** Heavy left, empty right (or vice versa) without that imbalance serving the content. *Fix:* either balance (move weight, add a Spacer with a real element) or commit harder to the asymmetry so it reads as deliberate.
- **Symmetric where asymmetric serves better.** A symmetric three-column grid where the three items aren't actually equal in importance. *Fix:* use an asymmetric split that mirrors actual hierarchy.
- **Redundant nesting.** Three Frames nested with no padding/background between, or two Stacks of the same axis nested. The tree could collapse one level. *Fix:* flatten until each level earns its presence.
- **Z-anchor mismatch.** A popover scaled from screen-center instead of from its trigger; a tooltip floating without a clear anchor. *Fix:* tie `transform-origin` to the trigger; visually anchor the floating element with a connector or proximity.
- **No edge story.** What happens at the viewport edge? At the top of scroll? At zero items? At 500 items? When text wraps to three lines? If you can't sketch each, the layout will break under real content.
- **No focal hierarchy in dark mode / mobile.** Dark mode often inverts gravity (saturated colors on dark surfaces have *more* gravity than the same colors on light). Run the gravity calculation again for the alternate surface. Same for mobile: an element that dominates on desktop may sit below the fold on mobile.

## A worked example

The user asks for a profile row component. You write:

```jsx
<div className="flex items-center gap-3 px-4 py-3 hover:bg-muted">
  <Avatar src={user.avatar} />
  <div className="flex flex-col">
    <span className="font-medium">{user.name}</span>
    <span className="text-sm text-muted-foreground">{user.email}</span>
  </div>
  <ChevronRight className="ml-auto text-muted-foreground" />
</div>
```

Mental render:

- **Bounding box**: row, full width of parent, padding 16/12.
- **Tree**: outer `Frame` (padded, hover surface) → `Stack(axis=horizontal, alignment=center, gap=12)` → [`Avatar(fit)`, `Stack(axis=vertical)` containing `Text(name, semibold)` and `Text(email, sm muted)`, `Spacer`, `Icon(chevron, muted)`].
- **2D**:
  ```
  [O] Sarah Chen                          >
      sarah@example.com
  ```
- **Gravity**: name has the most (semibold on default surface). Email recedes (sm + muted). Chevron is the lightest signal (muted icon). Avatar provides anchor weight on the left.
- **Focal point**: name — matches intent (this is a person row, the person's name should dominate).
- **Smell tests**: no orphans, hierarchy on two axes (weight + color), proximity groups name+email, Spacer pushes chevron right intentionally, single gap value is fine because it's a tight repeating pattern.

Pass. The code matches what the row should look like.

Now the same layout in SwiftUI:

```swift
HStack(alignment: .center, spacing: 12) {
  Avatar(url: user.avatar)
  VStack(alignment: .leading) {
    Text(user.name).fontWeight(.medium)
    Text(user.email).font(.subheadline).foregroundStyle(.secondary)
  }
  Spacer()
  Image(systemName: "chevron.right").foregroundStyle(.secondary)
}
.padding(.horizontal, 16).padding(.vertical, 12)
```

Same mental render. Same primitives, same properties, same gravity, same focal point. The framework changed; the layout didn't. **That's the point of the syntax-agnostic vocabulary** — once the mental render is right, emitting the framework-specific code is a mechanical translation.

## When to write the IR explicitly

For any layout with more than ~8 leaf nodes, more than 2 levels of nesting, any z-stacking, or any responsive breakpoints — write the IR out as a planning block before the code. Format it however helps you reason; the act of writing it is what does the work. Research has shown a measurable lift from explicit layout planning (ScreenCoder, MLS, Self-planning Code Generation). The skill is making this *cheap* enough that it's worth doing every time the layout is non-trivial.

## What this protocol does not do

- It does not pick the right design — it surfaces whether the design you have is rendered correctly. Pair it with `composition.md` for the design judgment layer.
- It does not catch aesthetic problems (wrong colors, ugly easing, missing polish details). Pair it with the polish principles in `SKILL.md`.
- It does not handle motion, only static layout. For motion reasoning, see `animations.md`.

## Sources

- Wang et al., *ScreenCoder* — https://arxiv.org/abs/2507.22827
- Jiang et al., *Self-planning Code Generation* — https://arxiv.org/abs/2303.06689
- *LLMs as Layout Designers / LaySPA* — https://arxiv.org/abs/2509.16891
- *Modular Layout Synthesis* — https://arxiv.org/html/2512.18996v1
- *Visual Perception in Text Strings / ASCIIBench* — https://arxiv.org/html/2410.01733v2
- *Large Language Models Understand Layout* — https://arxiv.org/html/2407.05750v1
- Google, *A2UI* (cross-framework UI protocol, runtime not reasoning) — https://github.com/google/A2UI
