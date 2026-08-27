---
name: taste
description: Product-design judgment for creating and polishing UIs. Use when starting any new screen, component, or page; when reviewing UI code; when output feels generic or "AI-made"; when deciding hierarchy, density, layout, or type system; or when applying polish details — animation, easing, hit areas, typography, surfaces. Triggers on "design X", "build a UI for X", "make this feel better", "this looks off", "looks like AI made it", and any UI-creation or UI-review task.
---

# Taste

> *"With each prompt, we're trying to outsource not just labor, but the craft itself. Quality is the deliberate act of caring."* — Karri Saarinen, Linear, *Why is quality so rare?*

Taste, in 2026, is what you refuse. The default AI output — centered max-width hero, indigo accent, three feature cards, `rounded-2xl`, Inter — exists because the model collapses to the mean of its training data when given a vague brief. The job of this skill is to install the **judgment to refuse the defaults** and the **vocabulary to choose what goes in their place**, then the **detail-level polish** that separates a good design from a finished one.

This skill runs in three layers. Apply them in order.

| Layer | When | File |
|---|---|---|
| **1. Composition** | Before any code on a new surface. The pre-code interview, system, hierarchy, density, real content, state coverage. | [composition.md](composition.md) |
| **2. Layout reading** | Mid-flight self-audit. A syntax-agnostic mental rendering protocol: render the layout in your head before/after writing it. | [layout-reading.md](layout-reading.md) |
| **3. Polish** | Once composition is right. The prescriptive details below — radii, easing, hit areas, surfaces, typography, animation, performance. | This file + topic refs |

Plus a cross-cutting audit:

| Audit | When | File |
|---|---|---|
| **AI-slop fingerprints** | Run before considering any UI done. Names the specific defaults the model reaches for, with replacements. | [ai-slop.md](ai-slop.md) |

For mobile-specific work (iOS 26 / Liquid Glass, Material 3 Expressive, React Native), pair this skill with `mobile-product-design` if the project has it. For bold aesthetic direction (when the brief calls for distinctive creative voice), pair with `frontend-design`.

---

## Part 1 — Creating new UI

The full process is in [composition.md](composition.md). The minimum-viable version, to keep in your head every time:

1. **Interview the surface** — one-sentence job, target user in their state, primary/secondary/tertiary (cut one), focal point, tool surface or content surface.
2. **Pick a system** — type scale (4–6 sizes), weight palette (2–3), color roles, spacing scale, one radius, an opinionated reference product (not "clean" or "modern").
3. **Compose with reduction** — exactly one focal point, differentiate roles on ≥2 axes, reduce scope before reducing quality.
4. **Group with proximity** — borders and surfaces are last resorts. Container soup is a smell.
5. **Density is value / (time × space)** — match density to surface type. *Simple ≠ sparse; simple = no unjustified element.*
6. **Real content always** — longest realistic strings, real numbers with `tabular-nums`, cardinality range from 0 to 500, no Lorem.
7. **State coverage from day one** — empty / loading / error / partial designed alongside the happy path.
8. **Render it in your head** before code — see [layout-reading.md](layout-reading.md).
9. **Audit against the AI-slop fingerprints** — see [ai-slop.md](ai-slop.md).
10. **Then** apply Part 2 below.

---

## Review output contract

When reviewing UI code, lead with a markdown table. Do not use loose `Before:` / `After:` prose blocks.

| Before | After | Why |
| --- | --- | --- |
| `transition: all 300ms` | `transition: transform 200ms cubic-bezier(0.23, 1, 0.32, 1)` | Specify exact properties and use a stronger curve. |
| `transform: scale(0)` | `transform: scale(0.95); opacity: 0` | Entrances should have a visible shape instead of appearing from nothing. |
| `ease-in` on dropdown | `ease-out` or the default custom ease-out | UI should respond immediately; `ease-in` delays the moment users watch most closely. |
| `transform-origin: center` on menu | `transform-origin: var(--radix-dropdown-menu-content-transform-origin)` | Anchored surfaces should reveal from their trigger. |
| 200ms highlight on arrow-key change | no animation | Keyboard actions already happened; motion makes the UI feel late. |
| 400ms dropdown | ~180ms ease-out | Product UI must feel faster than the work it wraps. |
| Toast in from bottom, out to the side | same enter/exit vector | Spatial consistency is what makes swipe-to-dismiss feel attached. |

Use one row per issue. Keep the `Why` column brief and actionable.

---

## Part 2 — Polish details

The compounding small things. Apply these once composition is right; applying them on a generic structure produces a polished generic UI.

### Surfaces and structure

1. **Concentric border radius.** Outer radius = inner radius + padding. Mismatched radii on nested elements is the most common thing that makes interfaces feel off.
2. **Optical over geometric alignment.** When geometric centering looks off, align optically. Buttons with icons, play triangles, asymmetric icons all need manual adjustment.
3. **Shadows over borders.** Layer multiple transparent `box-shadow` values for natural depth. Shadows adapt to any background; solid borders don't.
4. **Contact + ambient shadows for elevation.** Real objects cast two shadows — a tight contact shadow and a soft ambient cast. One blurry shadow looks CGI. As elevation increases: contact fades, ambient grows and softens. See [surfaces.md](surfaces.md#elevation-shadows-contact--ambient).
5. **Image outlines.** Add a subtle `1px` outline with low opacity to images for consistent depth.
6. **Match browser chrome to your theme.** Set `color-scheme` on `<html>` and ship light + dark `<meta name="theme-color">` tags. See [surfaces.md](surfaces.md#match-browser-chrome-to-dark-mode).

### Typography

7. **Typographic hierarchy through differentiation.** Distinct semantic roles must be visibly distinct across **at least two axes** — size, weight, color, case, tracking. Not just size. See [typography.md](typography.md#hierarchy-through-differentiation).
8. **Font smoothing.** Apply `-webkit-font-smoothing: antialiased` to the root layout on macOS for crisper text.
9. **Tabular numbers.** `font-variant-numeric: tabular-nums` for any dynamically updating numbers, prices, timestamps, counters.
10. **Text wrapping.** `text-wrap: balance` on headings; `text-wrap: pretty` for body to avoid orphans.
11. **Prevent iOS input zoom.** Safari zooms inputs with `font-size < 16px`. Set `input, select, textarea { font-size: 16px }` on mobile breakpoints. Don't use `maximum-scale=1`. See [typography.md](typography.md#prevent-ios-input-zoom).

### Animation and motion

12. **Purpose, then frequency, then speed — or nothing.** Name the job (explain, tactile, spatial consistency, rare delight) before writing motion. Keyboard-initiated actions never animate. High-frequency tools (cmd-K, palettes, list arrowing) get zero motion. Product UI stays under 300ms; a faster spinner reads as a faster load. Sometimes the best animation is no animation. See [animations.md](animations.md#should-it-animate-at-all).
13. **Pick curves deliberately, never `ease-in` for UI.** CSS built-ins look generic. Default ease-out: `cubic-bezier(0.23, 1, 0.32, 1)`. Bidirectional: `cubic-bezier(0.77, 0, 0.175, 1)`. iOS-style sheets: `cubic-bezier(0.32, 0.72, 0, 1)`. `ease-in` only when an element is leaving the viewport. See [animations.md](animations.md#easing-vocabulary).
14. **Scale duration with element size.** Button press 100–160ms, tooltip 125–200ms, menu ~180ms (150–250ms), modal/drawer 200–500ms. Hard ceiling: 300ms for anything sub-modal. See [animations.md](animations.md#duration-scale).
15. **Interruptible animations.** CSS transitions for interactive state changes — they can be interrupted. Reserve keyframes for staged sequences that run once.
16. **`@starting-style` for interruptible enter.** Keyframe animations restart from frame zero on interruption; CSS transitions with `@starting-style` retarget smoothly. Watch specificity: inline `element.style` beats `@starting-style`. See [animations.md](animations.md#starting-style-for-interruptible-enter).
17. **Split and stagger enter animations.** Don't animate a single container. Break content into semantic chunks and stagger each with ~100ms delay. First-load heroes only — not tab switches.
18. **Subtle exit animations, same vector as enter.** Small fixed `translateY`, shorter than enter. Menus fade out; they do not travel off-screen. See [animations.md](animations.md).
19. **Anchor reveals to their trigger.** Popovers/menus scale from their trigger, not their own center. Use `transform-origin: var(--radix-popover-content-transform-origin)`. Enter from `scale(0.95)` + `opacity: 0`. See [animations.md](animations.md#transform-origin-matters).
20. **Contextual icon animations.** Animate icons with `opacity`, `scale`, and `blur` instead of toggling visibility. Scale 0.25→1, opacity 0→1, blur 4px→0. With Motion: `transition: { type: "spring", duration: 0.3, bounce: 0 }` — bounce always 0. Without: cross-fade with CSS transitions using `cubic-bezier(0.2, 0, 0, 1)`.
21. **Scale on press.** Subtle `scale(0.96)` on click. Always `0.96`. Never below `0.95` — feels exaggerated. Add a `static` prop to disable when motion would distract.
22. **Skip animation on page load.** `initial={false}` on `AnimatePresence`. Verify it doesn't break intentional entrance animations.
23. **Kill animation on high-frequency and keyboard paths.** Anything triggered 100+ times/day, plus every keyboard-driven highlight — animation is friction. See [animations.md](animations.md#skip-animation-on-high-frequency-actions).
24. **Honor `prefers-reduced-motion` — kill transforms, keep opacity.** Vestibular users get sick from translate/scale. Strip transforms; opacity fades aid comprehension without triggering motion sickness. See [animations.md](animations.md#respect-prefers-reduced-motion).
25. **Loading states: delay + minimum duration.** Spinners need 150–300ms **delay** before showing (skip if request resolves first) and 300–500ms **minimum visible** once shown. See [animations.md](animations.md#loading-states-delay--minimum-duration).
26. **Match motion frequency to motion cost.** Hundredth-time interactions get *no* animation; rare ones get the budget. Delight that fires daily becomes annoyance.
27. **Tooltips chain instantly.** Keep an initial hover delay to avoid accidental activation, but once one tooltip is open, adjacent tooltips should appear without delay or animation. See [animations.md](animations.md#tooltip-sequencing).
28. **Use springs for drag and decorative life, not chrome.** Springs are for interruptible gestures and rare decorative tracking. Toggles, menus, and toasts use ease-out — springs wobble. See [animations.md](animations.md#spring-animations).
29. **Use clip-path for controlled reveals.** `clip-path: inset(...)` can power active-tab color masks, hold-to-confirm fills, comparison sliders, and image reveals without extra layout churn. See [animations.md](animations.md#clip-path-patterns).

### Interaction

30. **Use `:focus-visible`, not `:focus`.** Rings show on keyboard focus only; pointer users read mouse-click rings as noise. See [surfaces.md](surfaces.md#focus-visible-not-focus).
31. **Minimum hit area.** Interactive elements need at least 40×40px hit area on web; 44pt minimum on iOS, 48dp on Android (see `mobile-product-design`). Extend with a pseudo-element if visible element is smaller. Never overlap two hit areas.
32. **Touch devices do not get hover motion.** Gate hover-only transforms behind `@media (hover: hover) and (pointer: fine)`. See [animations.md](animations.md#touch-device-hover).
33. **Gestures need physics and capture.** Flick velocity, damped boundaries, pointer capture, and multi-touch guards make drag interactions feel intentional instead of brittle. See [animations.md](animations.md#gesture-and-drag-interactions).

### Performance

34. **Never `transition: all`.** Always specify exact properties: `transition-property: scale, opacity`. Tailwind's `transition-transform` covers `transform, translate, scale, rotate`.
35. **Animate compositor-friendly properties.** Prefer `transform` and `opacity`; be careful with `filter` and `clip-path`; avoid animating dimensions, padding, or margins. See [performance.md](performance.md#animate-compositor-friendly-properties).
36. **Use `will-change` sparingly.** Only for `transform`, `opacity`, `filter`, or `clip-path`. Never `will-change: all`. Only when you notice first-frame stutter.
37. **Prefer CSS/WAAPI under page-load pressure.** JS animation libraries can miss frames when the main thread is busy; CSS animations and WAAPI keep predetermined motion closer to the browser. See [performance.md](performance.md#css-and-waapi-under-load).

---

## Common mistakes

| Mistake | Fix |
|---|---|
| Brief is "clean modern dashboard" | Anchor to a specific reference (Bloomberg-density, Linear-focused-list, etc.). See [composition.md](composition.md#2-system-over-components). |
| No focal point — everything has equal weight | Pick one element, amplify gravity (size/weight/saturation/isolation), reduce gravity on the rest. See [layout-reading.md](layout-reading.md). |
| Three feature cards in a symmetric grid | Editorial split, single annotated screenshot, or asymmetric grid. See [ai-slop.md](ai-slop.md#layout-fingerprints). |
| Indigo/purple primary, Inter, gradient hero, glass-on-orb | Mode collapse to AI default. Refuse by name. See [ai-slop.md](ai-slop.md#the-stop-list). |
| Container soup — nested wrappers with backgrounds and padding | Flatten until structure is legible from spacing alone. Borders/surfaces last resort. |
| Uniform `gap-4` everywhere | Spacing as rhythm — tight where related, generous where structure breaks. |
| `rounded-2xl` on every element | One intentional radius for the system. |
| Lorem ipsum or placeholder content | Real content, longest realistic strings, real numbers. |
| Happy path only | Design empty / loading / error / partial alongside. |
| Same border radius on parent and child | Outer = inner + padding. |
| Icons look off-center | Adjust optically. |
| Hard borders between sections | Layered `box-shadow` with transparency. |
| Numbers cause layout shift | `tabular-nums`. |
| Heavy text on macOS | `antialiased`. |
| Animation plays on page load | `initial={false}` on `AnimatePresence`. |
| `transition: all` | Specify properties. |
| First-frame stutter | `will-change: transform` (sparingly). |
| Tiny hit areas | Extend with pseudo-element. |
| Heading + button + label all look similar | Differentiate ≥2 axes. |
| In-content headings smaller than page `h1` | Override `prose-h1` / `prose-h2` to match site scale. |
| UI feels laggy | Replace `ease-in` with `cubic-bezier(0.23, 1, 0.32, 1)`. |
| Menu pops from screen center | `transform-origin` to Radix anchor variable. |
| Animation plays every cmd-K / list arrow | Kill it. Keyboard paths never animate. |
| Motion with no named purpose | Don't animate. "The library has an enter" is not a purpose. |
| Springs on toggles/toasts | Ease-out. Springs wobble on chrome. |
| Toast enters one way, exits another | Same vector. |
| Ring flashes on mouse click | `:focus-visible`. |
| Dropdown shadow looks like a Photoshop blur | Layer contact + ambient. |
| Spinner flashes on fast requests | 200ms show-delay + 400ms min-visible. |
| iOS zooms on input tap | Mobile `input` `font-size: 16px`. |
| White scrollbar in dark mode | `color-scheme: dark` on `<html>`. |
| Tooltip delay repeats across a toolbar | Skip delay and animation after the first tooltip is open. |
| Hover transform sticks on touch | Gate hover effects with `@media (hover: hover) and (pointer: fine)`. |
| Drag dismissal ignores quick flicks | Include velocity as well as distance threshold. |
| CSS variable updates every drag frame | Write `transform` on the moving element instead of an inheritable variable on a parent. |

---

## Review checklist

### Composition (run before code)
- [ ] One-sentence job statement for the surface
- [ ] Target user named, in a specific state
- [ ] Primary / secondary / tertiary identified, at least one cut
- [ ] Focal point chosen explicitly
- [ ] Tool vs. content surface decided; density matches
- [ ] Type scale, weight palette, color roles, spacing scale, single radius committed
- [ ] Reference product is specific, not adjectival — stolen modules, not invented personality
- [ ] Real content used for layout, no Lorem
- [ ] Empty / loading / error / partial states designed
- [ ] Cardinality range covered (0, 1, 5, 50, 500 items)
- [ ] One accent per view; status not by color alone; labels are visible; UI chrome is sentence case

### Layout (run mid-flight as self-audit)
- [ ] Mental render matches intent at each level
- [ ] ASCII sketch drawn for any non-trivial layout
- [ ] Z-layers tracked separately with anchor + trigger
- [ ] Gravity computed; heaviest element matches focal point
- [ ] No flat hierarchy, no ungrouped siblings, no uniform density, no redundant nesting

### AI-slop audit (run before done)
- [ ] No reach for indigo/purple as default accent
- [ ] No `Inter`-only typography
- [ ] No centered max-w hero + 3-col feature grid
- [ ] No `rounded-2xl` on every element
- [ ] No glass-on-orb, no pure `#000`/`#fff`
- [ ] Per-tool fingerprints checked (v0, Lovable, Claude tells)

### Polish (run last)
- [ ] Concentric border radius
- [ ] Icons optically centered
- [ ] Shadows used over borders, layered contact + ambient
- [ ] Roles differ on ≥2 axes; prose headings match site scale
- [ ] `tabular-nums` on dynamic numbers; balance/pretty on text
- [ ] Font smoothing applied
- [ ] No `ease-in` on UI that stays on screen
- [ ] Durations scale with element size
- [ ] Popovers/menus use `transform-origin` tied to trigger
- [ ] Tooltips skip delay/animation after first tooltip is open
- [ ] Hover transforms are gated to fine-pointer hover devices
- [ ] Drag gestures include velocity, damping, pointer capture, and multi-touch protection
- [ ] Clip-path reveals avoid layout churn where a mask is the simpler model
- [ ] Scale-on-press on buttons (`0.96`)
- [ ] `AnimatePresence` uses `initial={false}` for default-state elements
- [ ] No `transition: all`; `will-change` only on transform/opacity/filter/clip-path
- [ ] CSS variables are not updated on a large parent every animation frame
- [ ] CSS/WAAPI considered for predetermined motion under load
- [ ] Hit areas ≥40×40px (web) / 44pt (iOS) / 48dp (Android)
- [ ] `:focus-visible` everywhere visible rings appear
- [ ] Loading spinners gated by show-delay + min-visible
- [ ] `prefers-reduced-motion` strips transforms, keeps opacity
- [ ] Mobile inputs ≥16px
- [ ] `color-scheme` + `theme-color` set
- [ ] High-frequency and keyboard paths skip animation
- [ ] Every motion has a named purpose; delight is reserved for rare surfaces

---

## Reference files

- [composition.md](composition.md) — creating new UI from scratch: pre-code interview, system, hierarchy, density, state coverage
- [layout-reading.md](layout-reading.md) — syntax-agnostic mental rendering protocol; render the layout in your head before/after coding
- [ai-slop.md](ai-slop.md) — the specific fingerprints of AI-generated UI in 2025–2026 with replacements
- [typography.md](typography.md) — text wrapping, smoothing, tabular numbers, hierarchy details
- [surfaces.md](surfaces.md) — radii, alignment, shadows, image outlines, focus, hit areas, theme chrome
- [animations.md](animations.md) — purpose/frequency/speed gate, easing, duration, enter/exit, transform-origin, springs, tooltips, gestures, clip-path, reduced motion, loading
- [performance.md](performance.md) — compositor-friendly properties, transition specificity, `will-change`, CSS/WAAPI under load

## External pairings

- **`mobile-product-design`** — iOS 26 / Liquid Glass, Material 3 Expressive, React Native specifics. Use when the surface is a mobile app.
- **`frontend-design`** — bold aesthetic direction, distinctive creative voice. Use when the brief calls for a strong visual personality.
- **`shadcn`** — component implementation. Use *after* composition decisions are made, not as a substitute for them.
- **`improve-animations` / `animate-expo` / `review-animations`** — when the job is a motion audit, Expo implementation, or a single-diff motion review. Taste decides whether motion belongs; those skills execute or plan it.
- **[UI Skills](https://www.ui-skills.com/)** — specialist catalog (audit/plan skills, playbook). Route there for a named audit. Do **not** ingest component dumps (coss, reui, shadcn galleries) or a design-system checklist as a substitute for this skill's judgment.

---

## Sources

The composition and AI-slop layers are grounded in:

- Karri Saarinen, *Why is quality so rare?* — https://linear.app/now/why-is-quality-so-rare
- Karri Saarinen, *10 rules for crafting products that stand out* (Config 2025) — https://www.figma.com/blog/karri-saarinens-10-rules-for-crafting-products-that-stand-out/
- Matt Ström-Awn, *UI Density* — https://matthewstrom.com/writing/ui-density/
- Rauno Freiberg, *Invisible Details of Interaction Design* — https://rauno.me/craft/interaction-design
- *AI's Purple Problem* — https://dev.to/jaainil/ai-purple-problem-make-your-ui-unmistakable-3ono
- *Awesome Claude Design* — https://github.com/rohitg00/awesome-claude-design
- Sam Henri Gold, *truth to materials* — https://samhenri.gold/blog/20260418-claude-design/

The layout-reading protocol is grounded in:

- ScreenCoder (Wang et al., 2025) — https://arxiv.org/abs/2507.22827
- LaySPA / *LLMs as Layout Designers* — https://arxiv.org/abs/2509.16891
- ASCIIBench / *Visual Perception in Text Strings* — https://arxiv.org/html/2410.01733v2
- Self-planning Code Generation — https://arxiv.org/abs/2303.06689

Motion judgment is grounded in Emil Kowalski, *[You don't need animations](https://emilkowal.ski/ui/you-dont-need-animations)*: purpose, then frequency, then speed; keyboard paths never animate; sometimes the best animation is none. Polish details remain practitioner-distilled from Rauno, Emil, Pete Lada, and current shadcn/Vercel/Linear practice. The UI Skills catalog is a routing surface, not a second principle set.
