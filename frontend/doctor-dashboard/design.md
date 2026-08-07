# Design — HF CDSS Doctor Dashboard (Chat)

Locked system for the clinical chat workbench. App routes share tokens in `tokens.css` and Tailwind `@theme` in `src/index.css`.

## Genre

modern-minimal

## Macrostructure family

- App / chat: **Workbench** — sidebar conversation rail · central thread · resizable clinical evidence panel

## Theme

- Paper: oklch(100% 0 0) / muted oklch(97.5% 0.004 145)
- Ink: oklch(16% 0.01 145)
- Accent: oklch(62% 0.12 166) (clinical green, aligned with `--color-primary`)

## Typography

- Display + body: Fira Sans
- Mono: Fira Code
- Headings: roman only, weight 600

## Motion

motion-cut — opacity/transform only, `prefers-reduced-motion` respected

## App pages

No hero enrichment. Function and panel tabs carry the UI.

## What pages MUST share

- Fira stack, clinical green accent, 4pt spacing tokens, shadcn button radii
