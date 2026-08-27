# Animations

Interruptible animations, enter/exit transitions, and contextual icon animations.

## Should it animate at all?

Decide in this order. Stop at the first no. Source: Emil Kowalski, *[You don't need animations](https://emilkowal.ski/ui/you-dont-need-animations)*.

1. **Purpose.** Name the job in one phrase. Valid jobs:
   - **Explain** — motion that teaches a mechanism a static frame cannot (Linear's Product Intelligence hero).
   - **Tactile response** — press scale, switch snap. The control is already on screen; motion confirms the hit.
   - **Spatial consistency** — the thing enters and leaves on the same vector so a swipe/dismiss gesture feels attached to it (Sonner: in from below, out the same way).
   - **Delight** — only if the user will rarely see it. A morphing feedback control is memorable once a week and irritating twenty times a day.
2. **Frequency.** Raycast opens hundreds of times a day with *no* animation. That is the correct product, not a missing flourish. If the user has a goal and will hit this path constantly, motion is friction.
3. **Speed.** Product UI has to feel faster than the work it wraps. A faster spinner reads as a faster load at identical latency. A `180ms` menu beats a `400ms` one. Sub-modal ceiling: `300ms`. Marketing pages may go longer; tools may not.

Hard refusals:

- **Keyboard-initiated actions never animate.** Arrowing a list, cmd-K, typeahead highlight — the key already happened. Motion makes the UI feel late and disconnected. Do not "soften" it with 80ms.
- **No purpose → no animation.** "The library has an enter transition" is not a purpose.
- **The goal is a great interface, not an animated one.** Sometimes the best animation is no animation.

If the answer is yes, then pick interruptibility, curve, origin, and reduced-motion below. Do not reverse this order.

## Interruptible Animations

Users change intent mid-interaction. If animations aren't interruptible, the interface feels broken.

Before writing animation code, reuse the purpose named above. If you skipped that gate, go back. Animation budget belongs on moments where motion clarifies the interface or makes rare interactions feel cared for.

### CSS Transitions vs. Keyframes

| | CSS Transitions | CSS Keyframe Animations |
| --- | --- | --- |
| **Behavior** | Interpolate toward latest state | Run on a fixed timeline |
| **Interruptible** | Yes — retargets mid-animation | No — restarts from beginning |
| **Use for** | Interactive state changes (hover, toggle, open/close) | Staged sequences that run once (enter animations, loading) |
| **Duration** | Adapts to remaining distance | Fixed regardless of state |

```css
/* Good — interruptible transition for a toggle */
.drawer {
  transform: translateX(-100%);
  transition: transform 200ms ease-out;
}
.drawer.open {
  transform: translateX(0);
}

/* Clicking again mid-animation smoothly reverses — no jank */
```

```css
/* Bad — keyframe animation for interactive element */
.drawer.open {
  animation: slideIn 200ms ease-out forwards;
}

/* Closing mid-animation snaps or restarts — feels broken */
```

**Rule:** Always prefer CSS transitions for interactive elements. Reserve keyframes for one-shot sequences.

## Spring Animations

Springs are for motion that should preserve momentum when interrupted: drag gestures, sheet snapping, mouse-tracking decoration, and playful state changes. They are usually the wrong default for professional dashboard controls.

```tsx
const rotation = useSpring(mouseX * 0.1, {
  stiffness: 100,
  damping: 10,
});
```

Use the duration/bounce API when available because it is easier to tune by feel:

```ts
{ type: "spring", duration: 0.5, bounce: 0.2 }
```

Keep bounce between `0.1` and `0.3` for playful surfaces, and use `bounce: 0` for serious product UI. Springs are especially useful when the user can reverse intent mid-motion; the animation should keep velocity instead of restarting from zero.

Do **not** use springs for routine toggles, menus, or toasts. Bounce reads as wobble on high-frequency chrome. Ease-out timing is the default there.

## Enter Animations: Split and Stagger

Don't animate a single large container. Break content into semantic chunks and animate each individually.

### Step by Step

1. **Split** into logical groups (title, description, buttons)
2. **Stagger** with ~50–100ms delay between semantic groups; **30–80ms** between sibling items in a list or grid. Anything slower than 100ms feels molasses on high-frequency surfaces.
3. **For titles**, consider splitting into individual words with ~80ms stagger
4. **Combine** `opacity`, `blur`, and `translateY` for the enter effect

### Code Example

```tsx
// Motion (Framer Motion) — staggered enter
function PageHeader() {
  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{
        visible: { transition: { staggerChildren: 0.1 } },
      }}
    >
      <motion.h1
        variants={{
          hidden: { opacity: 0, y: 12, filter: "blur(4px)" },
          visible: { opacity: 1, y: 0, filter: "blur(0px)" },
        }}
      >
        Welcome
      </motion.h1>

      <motion.p
        variants={{
          hidden: { opacity: 0, y: 12, filter: "blur(4px)" },
          visible: { opacity: 1, y: 0, filter: "blur(0px)" },
        }}
      >
        A description of the page.
      </motion.p>

      <motion.div
        variants={{
          hidden: { opacity: 0, y: 12, filter: "blur(4px)" },
          visible: { opacity: 1, y: 0, filter: "blur(0px)" },
        }}
      >
        <Button>Get started</Button>
      </motion.div>
    </motion.div>
  );
}
```

### CSS-Only Stagger

```css
.stagger-item {
  opacity: 0;
  transform: translateY(12px);
  filter: blur(4px);
  animation: fadeInUp 400ms ease-out forwards;
}

.stagger-item:nth-child(1) { animation-delay: 0ms; }
.stagger-item:nth-child(2) { animation-delay: 100ms; }
.stagger-item:nth-child(3) { animation-delay: 200ms; }

@keyframes fadeInUp {
  to {
    opacity: 1;
    transform: translateY(0);
    filter: blur(0);
  }
}
```

## Exit Animations

Exit animations should be softer and less attention-grabbing than enter animations. The user's focus is moving to the next thing — don't fight for attention.

### Subtle Exit (Recommended)

```tsx
// Small fixed translateY — indicates direction without drama
<motion.div
  exit={{
    opacity: 0,
    y: -12,
    filter: "blur(4px)",
    transition: { duration: 0.15, ease: "easeIn" },
  }}
>
  {content}
</motion.div>
```

### Full Exit (When Context Matters)

```tsx
// Slide fully out — use when spatial context is important
// (e.g., a card returning to a list, a drawer closing)
<motion.div
  exit={{
    opacity: 0,
    x: "-100%",
    transition: { duration: 0.2, ease: "easeIn" },
  }}
>
  {content}
</motion.div>
```

### Good vs. Bad

```css
/* Good — subtle exit */
.item-exit {
  opacity: 0;
  transform: translateY(-12px);
  transition: opacity 150ms ease-in, transform 150ms ease-in;
}

/* Bad — dramatic exit that steals focus */
.item-exit {
  opacity: 0;
  transform: translateY(-100%) scale(0.5);
  transition: all 400ms ease-in;
}

/* Bad — no exit animation at all (element just vanishes) */
.item-exit {
  display: none;
}
```

**Key points:**
- Use a small fixed `translateY` (e.g., `-12px`) instead of the full container height
- Enter and exit on the **same vector**. A toast that slides in from the bottom and fades out to the side breaks spatial memory and makes swipe-to-dismiss feel fake.
- Exit duration should be shorter than enter duration (150ms vs 300ms)
- Menus and dropdowns should close with a short fade, not a long travel off-screen
- Don't remove exit animations entirely on occasional surfaces — subtle motion preserves context. On high-frequency surfaces, skip both enter and exit.

## Contextual Icon Animations

When icons appear or disappear contextually (on hover, on state change), animate them with `opacity`, `scale`, and `blur` rather than just toggling visibility.

### Motion Example

```tsx
import { AnimatePresence, motion } from "motion/react";

function IconButton({ isActive, icon: Icon }) {
  return (
    <button>
      <AnimatePresence mode="popLayout">
        <motion.span
          key={isActive ? "active" : "inactive"}
          initial={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
          animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
          exit={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
          transition={{ type: "spring", duration: 0.3, bounce: 0 }}
        >
          <Icon />
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
```

### CSS Transition Approach (No Motion)

If the project doesn't use Motion (Framer Motion), keep both icons in the DOM and cross-fade them with CSS transitions. Because neither icon unmounts, both enter and exit animate smoothly.

The trick: one icon is absolutely positioned on top of the other. Toggling state cross-fades them — the entering icon scales up from `0.25` while the exiting icon scales down to `0.25`, both with opacity and blur.

```tsx
function IconButton({ isActive, ActiveIcon, InactiveIcon }) {
  return (
    <button>
      <div className="relative">
        <div
          className={cn(
            "absolute inset-0 flex items-center justify-center",
            "transition-[opacity,filter,scale] duration-300",
            "cubic-bezier(0.2, 0, 0, 1)",
            isActive
              ? "scale-100 opacity-100 blur-0"
              : "scale-[0.25] opacity-0 blur-[4px]"
          )}
        >
          <ActiveIcon />
        </div>
        <div
          className={cn(
            "transition-[opacity,filter,scale] duration-300",
            "cubic-bezier(0.2, 0, 0, 1)",
            isActive
              ? "scale-[0.25] opacity-0 blur-[4px]"
              : "scale-100 opacity-100 blur-0"
          )}
        >
          <InactiveIcon />
        </div>
      </div>
    </button>
  );
}
```

The non-absolute icon (InactiveIcon) defines the layout size. The absolute icon (ActiveIcon) overlays it without affecting flow.

### Choosing Between Motion and CSS

| | Motion (Framer Motion) | CSS transitions (both icons in DOM) |
| --- | --- | --- |
| **Enter animation** | Yes | Yes |
| **Exit animation** | Yes (via `AnimatePresence`) | Yes (cross-fade — icon never unmounts) |
| **Spring physics** | Yes | No — use `cubic-bezier(0.2, 0, 0, 1)` as approximation |
| **When to use** | Project already uses `motion/react` | No motion dependency, or keeping bundle small |

**Rule:** Check the project's `package.json` for `motion` or `framer-motion`. If present, use the Motion approach. If not, use the CSS cross-fade pattern — don't add a dependency just for icon transitions.

### When to Animate Icons

| Animate | Don't animate |
| --- | --- |
| Icons that appear on hover (action buttons) | Static navigation icons |
| State change icons (play → pause, like → liked) | Decorative icons |
| Icons in contextual toolbars | Icons that are always visible |
| Loading/success state indicators | Icon labels (text next to icon) |

**Important:** Always use exactly these values for contextual icon animations — do not deviate:
- `scale`: `0.25` → `1` (never use `0.5` or `0.6`)
- `opacity`: `0` → `1`
- `filter`: `"blur(4px)"` → `"blur(0px)"`
- `transition`: `{ type: "spring", duration: 0.3, bounce: 0 }` — **bounce must always be `0`**, never `0.1` or any other value

## Blur Bridges Crossfades

When a crossfade exposes two distinct objects overlapping, add a small blur during the transition so the eye reads it as one transformation. Keep it subtle: `filter: blur(2px)` is usually enough, and heavy blur is expensive in Safari.

```css
.button-content {
  transition: filter 200ms ease, opacity 200ms ease;
}

.button-content[data-transitioning="true"] {
  filter: blur(2px);
  opacity: 0.7;
}
```

## Scale on Press

A subtle scale-down on click gives buttons tactile feedback. Always use `scale(0.96)`. Never use a value smaller than `0.95` — anything below feels exaggerated. Use CSS transitions for interruptibility — if the user releases mid-press, it should smoothly return.

Not every button needs this. Add a `static` prop to your button component that disables the scale effect when the motion would be distracting.

### CSS Example

```css
.button {
  transition-property: scale;
  transition-duration: 150ms;
  transition-timing-function: ease-out;
}

.button:active {
  scale: 0.96;
}
```

### Tailwind Example

```tsx
<button className="transition-transform duration-150 ease-out active:scale-[0.96]">
  Click me
</button>
```

### Motion Example

```tsx
<motion.button whileTap={{ scale: 0.96 }}>
  Click me
</motion.button>
```

### Static Prop Pattern

Extract the scale class into a variable and conditionally apply it based on a `static` prop:

```tsx
const tapScale = "active:not-disabled:scale-[0.96]";

function Button({ static: isStatic, className, children, ...props }) {
  return (
    <button
      className={cn(
        "transition-transform duration-150 ease-out",
        !isStatic && tapScale,
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

// Usage
<Button>Click me</Button>           {/* scales on press */}
<Button static>Submit</Button>       {/* no scale */}
```

## Skip Animation on Page Load

Use `initial={false}` on `AnimatePresence` to prevent enter animations from firing on first render. Elements that are already in their default state shouldn't animate in on page load — only on subsequent state changes.

### When It Works

```tsx
// Good — icon doesn't animate in on mount, only on state change
<AnimatePresence initial={false} mode="popLayout">
  <motion.span
    key={isActive ? "active" : "inactive"}
    initial={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
    animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
    exit={{ opacity: 0, scale: 0.25, filter: "blur(4px)" }}
  >
    <Icon />
  </motion.span>
</AnimatePresence>
```

Works well for: icon swaps, toggles, tabs, segmented controls — anything that has a default state on page load.

### When It Breaks

Don't use `initial={false}` when the component relies on its `initial` prop to set up a first-time enter animation, like a staggered page hero or a loading state. In those cases, removing the initial animation skips the entire entrance.

```tsx
// Bad — initial={false} would skip the staggered page enter entirely
<AnimatePresence initial={false}>
  <motion.div initial="hidden" animate="visible" variants={...}>
    ...
  </motion.div>
</AnimatePresence>
```

Verify the component still looks right on a full page refresh before applying this.

## Easing Vocabulary

CSS built-ins (`ease`, `ease-in`, `ease-out`, `ease-in-out`) are too weak for polished UI — they look generic. Pick a curve deliberately per motion type.

| Motion | Curve | Use for |
| --- | --- | --- |
| Ease-out (default for reveals) | `cubic-bezier(0.23, 1, 0.32, 1)` | Most enter/hover/state transitions — snappy start, soft landing |
| Ease-in-out (bidirectional) | `cubic-bezier(0.77, 0, 0.175, 1)` | Tab switches, segmented controls, anything that can reverse mid-flight |
| iOS drawer/sheet | `cubic-bezier(0.32, 0.72, 0, 1)` | Bottom sheets, modal drawers, side panels |
| Icon crossfade | `cubic-bezier(0.2, 0, 0, 1)` | Contextual icon swaps (see icon animations section) |

**Never use `ease-in` for UI that stays on screen.** It delays perceived response and makes the interface feel laggy. Only acceptable when an element is leaving the viewport entirely (e.g., a toast sliding off-screen).

```css
/* Good — responsive feel */
.menu {
  transition: opacity 150ms cubic-bezier(0.23, 1, 0.32, 1),
              transform 150ms cubic-bezier(0.23, 1, 0.32, 1);
}

/* Bad — ease-in delays response on every interaction */
.menu {
  transition: opacity 150ms ease-in, transform 150ms ease-in;
}
```

## Duration Scale

One global duration makes small controls feel slow and large surfaces feel rushed. Scale duration with element size.

| Element | Duration |
| --- | --- |
| Button press feedback | 100–160ms |
| Tooltips, small popovers | 125–200ms |
| Dropdowns, selects, menus | 150–250ms (prefer ~180ms; 400ms feels like waiting) |
| Modals, drawers, full-screen overlays | 200–500ms |
| Hard ceiling for anything sub-modal | 300ms |

Product UI must feel fast. Speed is perceived performance, not decoration. Practical test: if a control animates slower than the time between two taps, it's too slow.

## Tooltip Sequencing

Tooltips need an initial delay so they do not flash during casual pointer movement. Once one tooltip is open, neighboring tooltips in the same toolbar should open instantly and skip their entrance animation. That makes dense toolbars feel fast without losing the accidental-hover guard on the first tooltip.

```css
.tooltip {
  transition: opacity 125ms cubic-bezier(0.23, 1, 0.32, 1),
              transform 125ms cubic-bezier(0.23, 1, 0.32, 1);
}

.tooltip[data-instant="true"] {
  transition-duration: 0ms;
}
```

## Transform Origin Matters

Popovers and menus should feel attached to their trigger. If they scale from their own center, the motion looks disconnected from what the user clicked.

```css
/* Radix exposes the anchor as a custom property — use it */
.popover-content {
  transform-origin: var(--radix-popover-content-transform-origin);
}

.dropdown-menu-content {
  transform-origin: var(--radix-dropdown-menu-content-transform-origin);
}
```

**Scale floor for enter animations:** `scale(0.95)` — not `scale(0.9)` or `scale(0)`. Combine with `opacity: 0`. This is distinct from the `scale(0.96)` press feedback — press is smaller motion because the element is already visible.

Modals and dialogs aren't anchored to a trigger — keep their `transform-origin: center`.

### Transform Details

Percentages in `translate()` are relative to the element's own size. Use `translateY(100%)` to hide a drawer or toast by exactly its height instead of hardcoding pixels.

`scale()` scales children too: text, icons, and internal spacing visually shrink together. That is why press feedback feels cohesive when kept subtle.

Use 3D transforms (`rotateX`, `rotateY`, `translateZ`, `transform-style: preserve-3d`) only when depth is part of the concept. For ordinary UI, fake depth with shadows and subtle 2D motion.

## Clip-path Patterns

`clip-path: inset(top right bottom left)` is a practical mask for reveals because it does not require layout changes. Each side eats into the element from that edge.

```css
.hidden-from-right {
  clip-path: inset(0 100% 0 0);
}

.visible {
  clip-path: inset(0 0 0 0);
}
```

Useful patterns:

- Active-tab color masks: duplicate the tab list, style the top copy as active, and clip it to the active tab for a seamless text/background color transition.
- Hold-to-confirm: animate an overlay from `inset(0 100% 0 0)` to `inset(0 0 0 0)` over the deliberate hold duration; snap back quickly on release.
- Image reveals: start from `inset(0 0 100% 0)` and animate to visible when in view.
- Comparison sliders: overlay two images and adjust the clipped side from drag position.

## Gesture and Drag Interactions

Do not rely on distance alone. Quick flicks should dismiss even when they do not cross a large threshold:

```ts
const elapsed = Date.now() - dragStartTime;
const velocity = Math.abs(dragDistance) / elapsed;

if (Math.abs(dragDistance) >= distanceThreshold || velocity > 0.11) {
  dismiss();
}
```

Add damping at natural boundaries instead of hard stops. Allow the gesture to continue with increasing friction so the surface feels physical rather than blocked by an invisible wall.

On pointer-driven drags, call `setPointerCapture` after drag start so the gesture continues if the pointer leaves the element. On touch, ignore additional touch points once a drag has started; switching fingers mid-drag should not make the element jump.

## Touch-device Hover

Touch devices can trigger hover styles on tap. Gate hover-only motion behind precise hover capability:

```css
@media (hover: hover) and (pointer: fine) {
  .action:hover {
    transform: scale(1.03);
  }
}
```

## Skip Animation on High-Frequency Actions

Any action a user triggers tens or hundreds of times a day turns animation into friction. Remove motion from your hottest paths. Keyboard paths are a hard zero regardless of how "delightful" the mock looks.

| Frequency | Treatment |
| --- | --- |
| Keyboard / typeahead / cmd-K / list arrowing | No animation. Ever. |
| 100+ times/day (repeated toggles, palette open) | No animation |
| Tens/day (navigation, tab switches) | Minimal — ≤100ms, no stagger |
| Occasional (modals, first-run sheets) | Full animation with enter/exit |
| Rare (onboarding, empty-state hero) | Delight is fine |

Test: open the surface ten times in a row, then drive it from the keyboard. If an animation plays every time, or if the highlight lags the key, kill it.

## Respect `prefers-reduced-motion`

Vestibular users get sick from translate/scale animations. But stripping *all* motion removes useful state cues. The right move is: kill transforms, keep opacity.

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  /* Re-enable opacity fades selectively — they aid comprehension without motion sickness */
  .fade {
    transition-duration: 200ms !important;
  }
}
```

Audit: for every `translate` or `scale` transition, ask whether the state change still reads with opacity alone. Usually yes.

## Loading States: Delay + Minimum Duration

A spinner that flashes for 80ms then vanishes reads as a glitch. A spinner that appears instantly on a request that resolves in 50ms creates phantom jank.

**Two gates:**

1. **Show-delay** of 150–300ms before the spinner/skeleton appears. If the request resolves first, no spinner ever shows.
2. **Minimum visible duration** of 300–500ms once shown, so it doesn't blink out.

```tsx
function useDelayedLoading(loading: boolean, { delay = 200, minVisible = 400 } = {}) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (loading) {
      const t = setTimeout(() => setShow(true), delay);
      return () => clearTimeout(t);
    }
    if (show) {
      const t = setTimeout(() => setShow(false), minVisible);
      return () => clearTimeout(t);
    }
  }, [loading, show, delay, minVisible]);
  return show;
}
```

## `@starting-style` for Interruptible Enter

Keyframe animations can't be interrupted gracefully — they restart from frame zero. `@starting-style` lets a CSS *transition* run on mount, so enter animations retarget smoothly like any other transition.

```css
.toast {
  opacity: 1;
  transform: translateY(0);
  transition: opacity 200ms cubic-bezier(0.23, 1, 0.32, 1),
              transform 200ms cubic-bezier(0.23, 1, 0.32, 1);

  @starting-style {
    opacity: 0;
    transform: translateY(8px);
  }
}
```

**Specificity gotcha:** `@starting-style` obeys normal CSS specificity. An ID selector or inline `element.style.transform` will beat it. For dynamic values, drive them through CSS custom properties rather than setting `.style` directly — that keeps specificity equal.

## Native CSS Springs via `linear()`

`linear()` lets you ship spring/bounce motion in vanilla CSS with no JS runtime cost. Generate values with [Linear Easing Generator](https://linear-easing-generator.netlify.app/) or [Easing Wizard](https://easingwizard.com/); don't hand-write them.

```css
html {
  /* Fallback for browsers without linear() */
  --spring-smooth: cubic-bezier(0.23, 1, 0.32, 1);
}

@supports (animation-timing-function: linear(0, 1)) {
  html {
    --spring-smooth: linear(
      0, 0.006, 0.024, 0.054, 0.094, 0.144, 0.202, 0.269, 0.342,
      0.421, 0.504, 0.591, 0.679, 0.768, 0.856, 0.941, 1.021, 1.093,
      1.156, 1.208, 1.246, 1.271, 1.283, 1.281, 1.267, 1.243, 1.211,
      1.173, 1.131, 1.087, 1.044, 1.004, 0.97, 0.942, 0.922, 0.91,
      0.907, 0.912, 0.925, 0.944, 0.969, 0.998, 1.03, 1.063, 1.094,
      1.124, 1.149, 1.17, 1.185, 1.194, 1.197, 1.194, 1.187, 1.175,
      1.161, 1.144, 1.126, 1.108, 1.091, 1.075, 1.062, 1.051, 1.043,
      1.038, 1.036, 1
    );
  }
}
```

**Use for:** drawer snap, overshoot on drop, celebratory micro-moments.
**Don't use for:** interruptible state transitions — `linear()` can't do inertia. Keep cubic-béziers for those.

## Debugging Animations

Review motion in slow mode before calling it done. Temporarily multiply durations by `2` to `5`, or use the browser animation inspector.

Check:

- Do colors and opacity create a single transformation, or two visible objects crossing through each other?
- Does the element start moving immediately, or does easing delay the user's feedback?
- Does the transform origin match the trigger?
- Are opacity, transform, blur, and color synchronized?

For touch interactions, test on real hardware when feasible. Simulators are useful, but physical devices expose gesture latency, scroll conflict, and multi-touch problems earlier.
