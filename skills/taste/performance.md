# Performance

Transition specificity, GPU compositing hints, and browser runtime pressure.

## Animate Compositor-friendly Properties

Prefer `transform` and `opacity`. They avoid layout and usually avoid paint, so the browser can composite them cheaply. Use `filter` and `clip-path` deliberately; they can composite, but heavy blur or complex masks still cost real work. Avoid animating `padding`, `margin`, `top`, `left`, `width`, or `height` unless the layout change is the point and the affected tree is tiny.

When moving something every frame during a drag, write to the moving element's `transform`:

```ts
element.style.transform = `translateY(${distance}px)`;
```

Do not update an inheritable CSS variable on a large parent every frame:

```ts
// Bad: every child inherits the changed variable and may need style recalculation.
container.style.setProperty("--swipe-amount", `${distance}px`);
```

## Transition Only What Changes

Never use `transition: all` or Tailwind's `transition` shorthand (which maps to `transition-property: all`). Always specify the exact properties that change.

### Why

- `transition: all` forces the browser to watch every property for changes
- Causes unexpected transitions on properties you didn't intend to animate (colors, padding, shadows)
- Prevents browser optimizations

### CSS Example

```css
/* Good — only transition what changes */
.button {
  transition-property: scale, background-color;
  transition-duration: 150ms;
  transition-timing-function: ease-out;
}

/* Bad — transition everything */
.button {
  transition: all 150ms ease-out;
}
```

### Tailwind

```tsx
// Good — explicit properties
<button className="transition-[scale,background-color] duration-150 ease-out">

// Bad — transition all
<button className="transition duration-150 ease-out">
```

### Tailwind `transition-transform` Note

`transition-transform` in Tailwind maps to `transition-property: transform, translate, scale, rotate` — it covers all transform-related properties, not just `transform`. Use this when you're only animating transforms. For multiple non-transform properties, use the bracket syntax: `transition-[scale,opacity,filter]`.

## Use `will-change` Sparingly

`will-change` hints the browser to pre-promote an element to its own GPU compositing layer. Without it, the browser promotes the element only when the animation starts — that one-time layer promotion can cause a micro-stutter on the first frame.

This particularly helps when an element is changing `scale`, `rotation`, or moving around with `transform`. For other properties, it doesn't help much — the browser can't composite them on the GPU anyway.

### Rules

```css
/* Good — specific property that benefits from GPU compositing */
.animated-card {
  will-change: transform;
}

/* Good — multiple compositor-friendly properties */
.animated-card {
  will-change: transform, opacity;
}

/* Bad — never use will-change: all */
.animated-card {
  will-change: all;
}

/* Bad — properties that can't be GPU-composited anyway */
.animated-card {
  will-change: background-color, padding;
}
```

### Useful Properties

| Property | GPU-compositable | Worth using `will-change` |
| --- | --- | --- |
| `transform` | Yes | Yes |
| `opacity` | Yes | Yes |
| `filter` (blur, brightness) | Yes | Yes |
| `clip-path` | Yes | Yes |
| `top`, `left`, `width`, `height` | No | No |
| `background`, `border`, `color` | No | No |

### When to Skip

Modern browsers are already good at optimizing on their own. Only add `will-change` when you notice first-frame stutter — Safari in particular benefits from it. Don't add it preemptively to every animated element; each extra compositing layer costs memory.

## CSS and WAAPI Under Load

JS animation libraries are excellent for dynamic, interruptible motion, but they still coordinate work from JavaScript. When the main thread is busy with page loads, data parsing, or expensive React renders, predetermined JS-driven animations can drop frames. Prefer CSS transitions/animations for known keyframes and use the Web Animations API when you need imperative control with browser-managed playback.

```ts
element.animate(
  [
    { clipPath: "inset(0 0 100% 0)" },
    { clipPath: "inset(0 0 0 0)" },
  ],
  {
    duration: 1000,
    fill: "forwards",
    easing: "cubic-bezier(0.77, 0, 0.175, 1)",
  },
);
```

For Motion/Framer Motion, shorthand values like `x`, `y`, and `scale` are convenient, but they are still scheduled through the library. If an animation stutters during load and the motion is predetermined, try CSS first. If staying in Motion, compare shorthand transforms against a full `transform` string and keep the approach that stays smooth in the target browser.
