# Hanami design system

The frosted panel and the petals are the only effects;
everything else is type, spacing and two colours. If a new screen needs
something not on this page, add it here first.

## Rules

- No gradients, glow, drop shadows, emoji icons or card grids.
- One typeface: Inter (bundled, OFL). Never more than two weights on one
  screen.
- Every size, gap and radius comes from the tables below.
- Pink means "this one": the highlighted row and nothing else.
- Motion is slow: no bouncing, no flashing.

## Colour

| Token | Value | Use |
|---|---|---|
| `panel` | `#17141d` at 72 % | panel fill over the blur |
| `edge` | white at 9 % | 1 px panel border |
| `text` | `#ece6ee` | names, title |
| `dim` | `#9b93a3` | labels, counts, hints |
| `accent` | `#f4b6c8` | highlighted row text |
| `pick` | accent at 14 % | highlighted row fill |
| `hover` | white at 5 % | row under the mouse, when not highlighted; letter tile behind a missing icon |
| `select` | accent at 35 % | selected text while renaming |
| `petal` | `#f7c4d3`, vein `#e9a3b8` | petals, 35–80 % opacity |

## Type (Inter)

| Role | Size | Weight |
|---|---|---|
| Title ("hanami") | 15 px | SemiBold |
| Game name | 14 px | Medium |
| Label, count, hint, footer | 11 px | Regular |

## Space and shape

- Scale: 4, 8, 12, 14, 20 px.
- Panel: 340 × 440, radius 16, padding 20, 1 px `edge` border.
- Rows: height 44, radius 10, inner padding 14, gap 8.
- Header: row padding 14 sideways, 6 below.

## Motion

- Row fill fades in 120 ms.
- Petals: 18 at 30 fps; each 7–13 px, falling 12–28 px/s, swaying 6–20 px,
  turning up to ±35°/s. Seeded, so every open looks the same.
- Panel open/close: 140 ms fade (to build).

## Platform

- Linux (KWin): blur behind a rounded region (`kwin-blur`). Without the
  Blur effect the panel is plain translucent.
- Windows 11: Acrylic behind the panel (to build).
