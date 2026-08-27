# Typography

Typography rendering details that make interfaces feel better.

## Hierarchy Through Differentiation

Distinct semantic roles (h1, h2, h3, body, button, label, metadata) must be visibly distinct — otherwise they compete for attention and the eye has no path through the page. Size alone isn't enough when the size gap is small; vary at least **two axes** from:

- **Size** (meaningful jumps — at least one full scale step, e.g. `text-2xl` → `text-base`)
- **Weight** (e.g. `font-semibold` heading vs `font-normal` body vs `font-medium` button)
- **Color** (`text-foreground` vs `text-muted-foreground` for metadata)
- **Case** (`uppercase` for labels/eyebrows)
- **Tracking** (`tracking-tight` on large headings, `tracking-wide` on small uppercase labels)

The main heading should carry the most presence — it sets the tone for the whole page. If your h1 and your primary button are the same weight and within one size step, the button is competing with the title. Pull them apart.

### Failure mode

Headings, buttons, and labels all land in the `font-medium` / `font-semibold` + `text-sm` / `text-base` range with the same color. Everything looks "clean" but nothing leads — users scan with no anchor.

### The fix

Assign each role an identity across **multiple axes** and keep it consistent:

```css
/* Good — clearly differentiated roles */
h1      { font-size: 2.5rem; font-weight: 600; letter-spacing: -0.02em; color: var(--fg); }
h2      { font-size: 1.5rem; font-weight: 600; letter-spacing: -0.01em; color: var(--fg); }
body    { font-size: 1rem;   font-weight: 400; color: var(--fg); }
button  { font-size: 0.875rem; font-weight: 500; color: var(--fg); }
.label  { font-size: 0.75rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; color: var(--fg-muted); }
.meta   { font-size: 0.8125rem; font-weight: 400; color: var(--fg-muted); }
```

### Nested content (MDX / prose)

Prose defaults from `@tailwindcss/typography` often under-size in-body headings so they feel *smaller* than the page `h1` — a content `h1` ending up at `text-xl font-medium` while the page `h1` is `text-3xl font-semibold` collapses hierarchy. Override `prose-h1` / `prose-h2` / `prose-h3` to match the site's scale, or never render a second `h1` inside a post and start at `h2`.

### Labels that "feel lost"

If metadata or stat labels use the same treatment as body copy, they'll disappear. Differentiate with **case + tracking** (`uppercase tracking-wide`) and **color** (muted foreground) — not just a smaller size, which just makes them harder to read.

### Checklist

- [ ] Every semantic role varies on at least two axes (size + weight, or weight + color, etc.)
- [ ] Primary heading is at least two scale steps above body
- [ ] Buttons are visibly lighter than headings (weight or size)
- [ ] Labels use uppercase + tracking or muted color — not just smaller size
- [ ] Prose-rendered headings (`prose-h1`, `prose-h2`) match the site's scale, not Tailwind defaults
- [ ] Nothing important shares size + weight + color with something unimportant

## Text Wrapping

### text-wrap: balance

Distributes text evenly across lines, preventing orphaned words on headings and short text blocks. **Only works on blocks of 6 lines or fewer** (Chromium) or 10 lines or fewer (Firefox) — the balancing algorithm is computationally expensive, so browsers limit it to short text.

```css
/* Good — even line lengths on short text */
h1, h2, h3 {
  text-wrap: balance;
}
```

```css
/* Bad — default wrapping leaves orphans */
h1 {
  /* no text-wrap rule → "Read our
     blog" instead of balanced lines */
}
```

```css
/* Bad — balance on long paragraphs (silently ignored, wastes intent) */
.article-body p {
  text-wrap: balance;
}
```

**Tailwind:** `text-balance`

### text-wrap: pretty

Optimizes the last line to avoid orphans using a slower algorithm that favors better typography over performance. Unlike `balance`, it works on longer text — use this for body copy where you want to minimize orphans without the 6-line limit.

```css
p {
  text-wrap: pretty;
}
```

### When to Use Which

| Scenario | Use |
| --- | --- |
| Headings, titles, short text (≤6 lines) | `text-wrap: balance` |
| Body paragraphs, descriptions | `text-wrap: pretty` |
| Code blocks, pre-formatted text | Neither — leave default |

## Font Smoothing (macOS)

On macOS, text renders heavier than intended by default. Apply antialiased smoothing to the root layout so all text renders crisper and thinner.

```css
/* CSS */
html {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

```tsx
// Tailwind — apply to root layout
<html className="antialiased">
```

### Good vs. Bad

```css
/* Good — applied once at the root */
html {
  -webkit-font-smoothing: antialiased;
}

/* Bad — applied per-element, inconsistent */
.heading {
  -webkit-font-smoothing: antialiased;
}
.body {
  /* no smoothing → heavier than heading */
}
```

**Note:** This only affects macOS rendering. Other platforms ignore these properties, so it's safe to apply universally.

## Tabular Numbers

When numbers update dynamically (counters, prices, timers, table columns), use tabular-nums to make all digits equal width. This prevents layout shift as values change.

```css
/* CSS */
.counter {
  font-variant-numeric: tabular-nums;
}
```

```tsx
// Tailwind
<span className="tabular-nums">{count}</span>
```

### When to Use

| Use tabular-nums | Don't use tabular-nums |
| --- | --- |
| Counters and timers | Static display numbers |
| Prices that update | Decorative large numbers |
| Table columns with numbers | Phone numbers, zip codes |
| Animated number transitions | Version numbers (v2.1.0) |
| Scoreboards, dashboards | |

### Caveat

Some fonts (like Inter) change the visual appearance of numerals with this property — specifically, the digit `1` becomes wider and centered. This is expected behavior and usually desirable for alignment, but verify it looks right in your specific font.

```css
/* With Inter font:
   Default:  1234  → proportional, "1" is narrow
   Tabular:  1234  → all digits equal width, "1" centered */
```

## Prevent iOS Input Zoom

Safari on iOS zooms into inputs whose computed `font-size` is less than `16px`, yanking the layout and often breaking the session. Fix at the source rather than disabling user zoom globally.

```css
/* Good — minimum 16px on mobile breakpoints prevents the zoom */
@media (max-width: 768px) {
  input,
  select,
  textarea {
    font-size: 16px;
  }
}
```

```html
<!-- Bad — disables pinch zoom for everyone, hurts accessibility -->
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
```

Prefer the font-size approach. If the design calls for smaller input text, keep the visual size small with `transform: scale()` or use a 16px font with tight line-height — don't go below 16px computed.

## Sentence case

UI chrome is sentence case: `Save chat`, `Search storyline`, `Try again`. Title Case looks like a marketing landing page inside a tool. All caps is for tiny tracked eyebrows only — never for buttons, tabs, or nav.

## Measure and heading rhythm

Body copy should land around **60–75 characters** per line. Wider than that and the eye loses the return; narrower and it chatters.

Short headings want a tight line-height (~`1.1`). Display sizes also want slightly tighter tracking — already in the hierarchy table above as `letter-spacing: -0.02em`. Don't apply body line-height (~1.5) to a two-word title.
