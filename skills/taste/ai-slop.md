---
name: ai-slop
description: Specific visual patterns designers consistently identify as "AI made this" in 2025-2026, with the mode-collapse mechanic that produces them and the replacements. Run this audit before considering any UI done.
type: reference
---

# AI slop: the fingerprints

LLMs producing UI converge to the **mean of their training data**, which is heavily Tailwind defaults plus shadcn dashboard blocks plus Linear/Vercel/Stripe imitators. The result: a recognizable visual signature designers can spot in seconds. *"AI isn't 'in love' with purple; we trained it to be average."* (https://dev.to/jaainil/ai-purple-problem-make-your-ui-unmistakable-3ono)

The fix is not "be more creative." The fix is **naming the specific defaults the model reaches for and refusing them by name.** Generic guidance ("avoid cliché") doesn't change behavior. Naming the pattern does, because the model recognizes itself in it.

This file is a checklist. Run it on any UI before considering it done.

## The mode-collapse mechanic

Every fingerprint below has the same root cause: when uncertain, the model picks the lowest-loss option from training data, which means the most *common* option, which means whatever shadcn / Tailwind docs / a Vercel template does by default. The model produces this even when the brief doesn't call for it, because the brief lacks specificity and the model fills the gap with the corpus mean.

Two consequences:

1. **Vague briefs collapse to the mean.** "Clean, modern dashboard" → centered hero, three feature cards, indigo accent, `rounded-2xl`, Inter, glass card on gradient. Specificity is the antidote: *"Bloomberg-density data table on a paper-cream background, single saturated red accent, JetBrains Mono numerics."*
2. **Default tokens win without resistance.** If the model sees `bg-indigo-500` in 10,000 examples and `bg-[#1c2a36]` in zero, it picks indigo unless explicitly stopped. Use OKLCH custom ramps or specific brand colors; never let the default win passively.

## Color fingerprints

| Pattern | Why it signals AI | Replacement |
|---|---|---|
| **`bg-indigo-500` / purple primary** for buttons, links, focus rings | Tailwind docs example for years; baked into training data | A custom OKLCH brand ramp; deep greens, petrol blues, terracotta, warm neutrals |
| **Purple-to-blue gradient hero text** | The literal "Lovable look"; indistinguishable from v0 dark mode | Solid color with weight + tracking carrying the emphasis; or a tightly scoped gradient on one element only |
| **Default shadcn neutral grays** with a single muted blue or teal accent | The "shadcn-ification" tell | Pick a real palette: warm or cool neutrals you committed to, one saturated accent that's *not* indigo or teal |
| **Pure `#000` on `#fff` (or inverted in dark mode)** | The model defaults to absolute values; designed UIs use off-blacks/off-whites | `~#0a0a0a` and `~#fafafa` in dark/light. Even slightly off feels considered. |
| **Glow/orb behind a centered card** in dark mode | The Lovable + v0 dark fingerprint | Layered surfaces with a real elevation system; depth from contrast, not from a blurred orb |

## Typography fingerprints

| Pattern | Why it signals AI | Replacement |
|---|---|---|
| **Inter or Geist as the only font** | Most-trained webfonts in the corpus | Pair a display face (Cabinet Grotesk, Bricolage, Cal Sans, GT Walsheim, a serif like Tiempos or Source Serif) with a refined body sans, plus a mono if numbers matter |
| **`text-2xl font-bold` for every important thing** | The model treats "important" as a single dimension | Differentiate roles across two axes minimum: size + weight, or weight + color, or case + tracking. See `typography.md`. |
| **Tiempos-style serif headline + generic sans body** as the "I tried to look custom" pairing | Now itself a fingerprint of "AI tried to escape AI slop" | Commit to a real type system; reference a specific product's vibe, not "modern serif + sans" |
| **No `font-variant-numeric: tabular-nums`** on prices, timestamps, counters | The model rarely sets it; mixed-width digits read as amateur | Always tabular-nums for any numeric column. See `typography.md`. |

## Layout fingerprints

| Pattern | Why it signals AI | Replacement |
|---|---|---|
| **Centered `max-w-7xl` hero, headline + subhead + single CTA** | The lowest-loss landing template | Editorial split (2/3 + 1/3); product-forward (the actual product as the hero); dense data-forward intro; left-aligned with intentional negative space |
| **Three feature cards in a symmetric grid** as section 2 | The lowest-loss "list 3 things" layout | Single annotated screenshot showing the feature in context; asymmetric grid where one feature dominates; long-form prose with inline visuals |
| **Testimonial carousel + logo cloud + FAQ accordion + CTA banner** | The full SaaS template stack | Cut at least two of these; replace logo cloud with a single trust signal that matters; replace the FAQ with inline answers under each feature |
| **Bento grid for "features"** | Was novel in 2023; now AI default | Use bento only when content cardinality genuinely differs (5+ features of varying weights). Otherwise, list, table, or editorial layout. |
| **Icon + label sidebar nav** lifted from shadcn dashboard blocks | Visible across every Cursor/v0 dashboard | Custom nav matching the product's actual hierarchy. If you have ≤5 sections, use a top bar or bottom tabs. Sidebar isn't a default. |

## Component / surface fingerprints

| Pattern | Why it signals AI | Replacement |
|---|---|---|
| **`rounded-lg` or `rounded-2xl` on every card and button** | No intentional radius hierarchy | Pick *one* radius for the system. Modals/sheets may use a larger one. Square corners are a valid choice and increasingly used. |
| **50px+ uniform padding** as a default | The "clean and spacious" model bias | A real spacing scale with rhythm. Tight where related, generous where the structure breaks. See `composition.md` §5. |
| **Container soup** — nested pills/cards with stacked padding and a 4px left accent bar | The model adds wrappers defensively when uncertain | Flatten until structure is legible from spacing alone. Borders/surfaces are last resorts. |
| **Glassmorphism + 20px backdrop-blur + gradient orb** | The dark-mode AI default; doubles as a contrast accessibility failure | Layered solid surfaces; backdrop-blur ≤5px when used; reserve glass for floating navigation only (and only on platforms where it's a real material — see `mobile-product-design`) |
| **Lucide icons everywhere** | Default in shadcn examples | Phosphor, Tabler, Heroicons, custom icons, or SF Symbols / Material Symbols if matching a platform. Mix only when intentional. |
| **Animated green status dot in the top-right of nav** | A common Claude/v0 tell | Drop unless there's a real status to show; if so, use the actual status color and tie it to a meaningful state. |
| **`border` on every group + `rounded` + `shadow` + `p-6`** | Cards-by-default | Proximity first; surface only when proximity isn't enough. See `composition.md` §4. |

## Per-tool tells

If the user's brief mentions one of these tools, the agent (you) is likely about to imitate its default. Recognize the convergence and resist:

- **v0 (Vercel)**: shadcn-out-of-the-box. Slate/zinc base, blue or cyan accent, `rounded-2xl`. Dark mode trends toward purple `#a855f7` accent, glass-blur card, gradient orb. The "wireframe with personality" look.
- **Lovable**: indigo CTAs, pink-to-purple gradients, the *"weirdly specific glow"*. Most aesthetically committed of the lot, also most recognizable.
- **Bolt**: template-y, generic. Functional but rarely beautiful. Often skips shadcn polish entirely.
- **Claude Artifacts / Claude Design**: Inter + system-sans, muted grays, blue primary, plus a distinctive teal `~#16d5e6` accent, serif headline + sans body, 4px left accent bar on cards.
- **Cursor / ChatGPT canvas**: least branded; pulls toward whichever shadcn block is closest in the training data, so its fingerprints overlap with v0's.

Net pattern: dark variants converge on `dark + neon purple/cyan + glass card + gradient orb`; light variants converge on `white + indigo + rounded cards + three-column features + Inter`. The differences are mostly accent-color biases on top of a shared shadcn skeleton.

## The stop list

Quick rules for the moment of reaching:

- Reaching for `bg-indigo-500` / purple → stop. Pick a brand color from an OKLCH ramp.
- Reaching for `Inter` → stop. Pair display + body, or pick something with character (Geist Mono, JetBrains Mono, Cabinet, Bricolage, a serif).
- Reaching for a centered hero with gradient headline → stop. Try editorial split, product-forward, or a dense data-first intro.
- Reaching for three feature cards in a symmetric grid → stop. Try one annotated screenshot, an asymmetric grid, or a single column.
- Reaching for `rounded-2xl` everywhere → stop. Pick one intentional radius. Square is fine.
- Reaching for `#000` / `#fff` in dark mode → stop. Use `~#0a0a0a` / `~#fafafa`.
- Reaching for glass-blur card on a gradient orb → stop. Use a layered surface system with real elevation tokens.
- Reaching for Lucide → stop only if the brief calls for character. Otherwise fine. (Default ≠ wrong; *unconsidered* default is wrong.)
- Reaching for 50px uniform padding → stop. Use a real spacing scale.
- Reaching for "clean, modern" as a brief → stop. Anchor to a specific reference: Bloomberg-density, Linear-focused-list, Stripe-Docs-code-first, Things-3-typography, Granola-paper-card.

## What's overrated / dead in 2026

Designers in 2025–2026 have explicitly walked back several patterns the model still reaches for:

- **Glassmorphism on content** — Apple revived it on iOS 26 nav layers; designers ripped the over-application. Glass on cards/lists/backgrounds is a tell. (See `mobile-product-design` for the iOS 26 specific rules.)
- **Purple-to-blue gradients** — fully into AI-fingerprint territory.
- **Inter-as-premium** — saturated past meaning.
- **The centered hero + 3-col + pricing template** — now the literal AI output.
- **Bento grids without intent** — 2023's novelty is 2026's cliché.
- **Hamburger menu as primary nav** — functionally dead in top-tier consumer apps.
- **Hand-keyframed Lottie animations for "delight"** — both platforms shifted to physics-based motion.
- **Metrics-driven design as the only authority** — Saarinen, Rule 10: *"Data can be a crutch."*

## Sources

- *AI's Purple Problem* — https://dev.to/jaainil/ai-purple-problem-make-your-ui-unmistakable-3ono
- *Escape AI slop landing page design* (Monet) — https://www.monet.design/blog/posts/escape-ai-slop-landing-page-design
- *Awesome Claude Design* (the eight Claude tells) — https://github.com/rohitg00/awesome-claude-design
- *The shadcn-ification of the internet* (Luis Ouriach) — https://medium.com/@disco_lu/the-shadcn-ification-of-the-internet-d3788c055c63
- *Dark mode design that doesn't look AI* — https://dev.to/raxxostudios/dark-mode-design-that-doesnt-look-ai-2cn3
- *Constraints, not adjectives* (MindStudio on Claude design) — https://www.mindstudio.ai/blog/claude-design-avoid-ai-slop-design-system
- Sam Henri Gold, *truth to materials* — https://samhenri.gold/blog/20260418-claude-design/
- *10 trends creatives are over in 2026* (Creative Boom) — https://www.creativeboom.com/insight/10-trends-creatives-are-so-over-in-2026/
- Karri Saarinen's 10 rules — https://www.figma.com/blog/karri-saarinens-10-rules-for-crafting-products-that-stand-out/
