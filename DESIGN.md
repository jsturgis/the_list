# The List: Design System

How The List looks, for the people and coding agents who change it. It's adapted from the Spotify entry in
[awesome-design-md](https://github.com/VoltAgent/awesome-design-md) (MIT), chosen on
[#71](https://github.com/jsturgis/the_list/issues/71). We took its feel (charcoal surfaces, one green accent,
weight-led type, pill controls) and left out its brand: its name, logo, imagery and proprietary fonts.

The colours below are the theme's semantic tokens, defined in `frontend/src/styles/globals.css`. A test keeps this file
and that stylesheet in sync: every token in one must be in the other, with the same light and dark values.

## 1. Visual Theme & Atmosphere

The List is a weekly listing of SF Bay Area Shows: dense, scannable text, not imagery. The design gets out of the
way so the Shows are what you see.

- **Dark is the primary look**: near-black canvas (`#121212`) with charcoal surfaces (`#181818`) stepping up toward
  the reader. Light mode is a soft grey canvas with white surfaces, built from the same rules.
- **One accent, used with intent.** Green marks what you can act on (filled buttons, active states) and what Steve
  recommends (Steve's Picks). It's never decoration.
- **Hierarchy by weight, not size.** Bold headliners against regular metadata. The type range is compact, made for
  scanning a week of Shows, not reading articles.
- **Rounded and touch-friendly.** Pill-shaped controls, softly rounded panels, no hard edges.
- **Flat.** Depth comes from surface steps, not shadows.

## 2. Colour Palette & Roles

Use these tokens through Tailwind's colour utilities (`bg-surface`, `text-ink-muted`, `border-line`, `bg-accent`,
`text-on-accent`, `bg-pick`…). Every token switches with the system's light/dark setting, so components never need a
`dark:` colour variant. Values in the form `red-600` are Tailwind palette colours.

| Token | Role | Light | Dark |
|---|---|---|---|
| **Surfaces** | | | |
| `page` | The page behind everything | `#f6f6f6` | `#121212` |
| `surface` | Cards, Show rows, list panels, the header | `#ffffff` | `#181818` |
| `panel` | The filter panel | `#ffffff` | `#181818` |
| `field` | Form fields | `#ededed` | `#2a2a2a` |
| `muted` | Neutral chips and quiet backgrounds (flags, Genre tags) | `#ededed` | `#2a2a2a` |
| `muted-hover` | Hover on `muted` | `#e2e2e2` | `#333333` |
| `surface-hover` | Hover on a card or row | `#f0f0f0` | `#252525` |
| `field-active` | The highlighted option in a list (Genre combobox) | `#e2e2e2` | `#333333` |
| **Text and icons** | | | |
| `ink` | Headings, headliners, main text | `#121212` | `#ffffff` |
| `ink-soft` | Secondary text: Venue lines, detail values | `#3d3d3d` | `#cbcbcb` |
| `ink-muted` | Meta text: times, prices, ages, supports, captions | `#5c5c5c` | `#b3b3b3` |
| `ink-faint` | Decorative icons, placeholders | `#808080` | `#7c7c7c` |
| **Lines** | | | |
| `line` | Borders | `#e2e2e2` | `#2a2a2a` |
| `line-subtle` | Dividers between rows, the header rule | `#ececec` | `#222222` |
| `line-strong` | Strong borders (form fields) | `#cfcfcf` | `#4d4d4d` |
| **Accent (green)** | | | |
| `accent` | Fill for primary buttons and active states. Never text on a light background | `#1ed760` | `#1ed760` |
| `accent-hover` | Hover on `accent` | `#1fdf64` | `#3be477` |
| `on-accent` | Text and icons on `accent`: always black | `#000000` | `#000000` |
| `link` | Links and any green text: the text-safe green | `#117a37` | `#1ed760` |
| `accent-soft` | Tinted banners (special events) | `#e8f9ee` | `#10291a` |
| `accent-soft-line` | Their border | `#b5ecc8` | `#1b4d2d` |
| `accent-soft-ink` | Their text | `#0b4f24` | `#b8f5cd` |
| `accent-chip` | Small accent tags ("Local", "active") | `#d6f5e1` | `#143a22` |
| `accent-chip-ink` | Their text | `#0d6b30` | `#6ff09b` |
| **Steve's Pick** | | | |
| `pick` | A Steve's Pick card or row | `#e8f9ee` | `#1b2a20` |
| `pick-hover` | Its hover | `#dcf6e6` | `#213528` |
| `pick-line` | Its border and star | `#117a37` | `#1ed760` |
| **Inverse** | | | |
| `inverse` | Toasts | `#121212` | `#ffffff` |
| `on-inverse` | Text on `inverse` and on `strong` | `#ffffff` | `#121212` |
| `inverse-muted` | Muted text on toasts | `#b3b3b3` | `#666666` |
| `strong` | The neutral filled button (Website) | `#121212` | `#ffffff` |
| `strong-hover` | Its hover | `#2a2a2a` | `#e0e0e0` |
| **Status** | | | |
| `danger` | Cancelled, Sold out, errors | `red-600` | `red-400` |
| `danger-soft` | Their badge background | `red-100` | `color-mix(in oklab, red-900 40%, transparent)` |
| `warning` | Postponed, warnings | `yellow-700` | `yellow-400` |
| `warning-soft` | Their badge background | `yellow-100` | `color-mix(in oklab, yellow-900 40%, transparent)` |
| `success` | Benefit, success messages | `emerald-700` | `emerald-400` |
| `success-soft` | Their badge background | `emerald-100` | `color-mix(in oklab, emerald-900 40%, transparent)` |
| `info` | Matinee, information | `sky-700` | `sky-400` |
| `info-soft` | Their badge background | `sky-100` | `color-mix(in oklab, sky-900 40%, transparent)` |
| `hot` | Will Sell Out | `orange-700` | `orange-400` |
| `hot-soft` | Its badge background | `orange-100` | `color-mix(in oklab, orange-900 40%, transparent)` |

**Pairs that must go together:**
- `accent` with `on-accent` (black)
- `strong` and `inverse` with `on-inverse`
- each `-soft` background with its own text token (`danger-soft` with `danger`, …)
- `accent-soft` with `accent-soft-ink`, and `accent-chip` with `accent-chip-ink`

**Brand colours we don't own:** the Spotify, SoundCloud and Bandcamp buttons on Band pages keep those services' own
colours, so people recognise them.

## 3. Typography Rules

- **Typeface:** **Figtree** (variable, SIL Open Font License), self-hosted through `@fontsource-variable/figtree`
  and preloaded by the layout. Fallback: `ui-sans-serif, system-ui, sans-serif`. Tailwind's `font-sans` is Figtree.
  There's no second family and no monospace in the UI.
- **Weights:** 800 for page titles; 700 for headings, headliners and button labels; 400 for everything else. Use
  600 sparingly.

| Role | Size | Weight | Notes |
|---|---|---|---|
| Page title (`h1`) | 24px (`text-2xl`); 30px (`text-3xl`) on detail pages | 800 | tracking −0.02em (global) |
| Date heading on the Shows list | 18px (`text-lg`) | 700 | sentence case, `ink` |
| Section heading (Lineup, Venue, Upcoming Shows) | 16px (`text-base`) | 700 | |
| Headliner in a Show row or card | 16px | 700 | `ink`; supports follow in `ink-muted`, prefixed "with" |
| Body | 16px / 14px (`text-sm`) | 400 | |
| Meta: time · price · age, captions | 12–14px (`text-xs`/`text-sm`) | 400 | `ink-muted` or `ink-soft` |
| Badges (flags, statuses) | 12px | 600 | statuses uppercase |
| Button labels | as the button | 700 | UPPERCASE, tracking 0.1em (global for `<button>`) |

## 4. Component Stylings

Components marked *(#72)* don't match this yet; that issue brings them in line.

- **Buttons**
  - *Primary:* `bg-accent` / `text-on-accent`, pill (`rounded-full`) *(#72)*, uppercase label. One per view, for
    the main action (Email me a sign-in link, Save).
  - *Neutral:* `bg-strong` / `text-on-inverse`.
  - *Outline:* `border-accent`, `text-link` on `surface` (Setup Alert).
  - *Quiet:* text-only in `ink-muted`, with an underline or a `muted` hover (Clear filters, Back).
- **Inputs and selects:** `bg-field`, pill-shaped *(#72)*, `ink` text, `ink-faint` placeholders. The focus ring is
  the accent *(#72)*.
- **Filter bar:** a `panel` block (8px radius) above the list, holding the Shows count, the Region, Search and
  Genre controls, Free only, Advanced filters and Setup Alert.
- **Show list item:**
  - Shows are listed as rows (`ShowRow`), not cards, in one `surface` panel per date (8px radius) with
    `line-subtle` dividers. Venue pages use the same row without the Venue line.
  - *Line 1:* status badge, then a star if it's a Steve's Pick, then the bold headliner and "with" the supports.
  - *Line 2:* Venue · city. No street address.
  - *Details:* door time · price · age, the flags, and the two calendar links (.ics and Google Calendar) for
    Upcoming Shows. The .ics links point to static files (`/calendar/<id>.ics`), never `data:` URIs. On desktop
    the details sit in a right-hand column; on phones each is its own line.
  - The headliner (an `h3`) links to the Show page, and its click area covers the row. The calendar links sit
    above it.
- **Steve's Pick:** the row or card takes `pick` (hover `pick-hover`) and a star in `pick-line`. No other emphasis.
- **Show flags and statuses:**
  - Cancelled: `danger`, uppercase badge
  - Postponed: `warning`, uppercase badge
  - Sold out: `danger`
  - Will Sell Out: `hot`
  - Benefit: `success`
  - Matinee: `info`
  - Pit Warning, Drink Tickets, No Re-entry: neutral, `muted` with `ink-soft`
  - Badges are small rounded labels (pills *(#72)*).
- **Detail pages (Show, Venue, Band):** a single readable column (`max-w-2xl`), with the h1 first and a Back link
  above. Facts are set as icon + label rows in `ink-soft`. Upcoming Shows use the Show list item.
- **Banners:** `accent-soft` with `accent-soft-line` and `accent-soft-ink` (special events).
- **Toasts:** `inverse` with `on-inverse`, 8px radius, at the bottom of the screen.
- **Links:** `text-link` for links in running text, underlined on hover. Navigation links (header, Back) are
  `ink-muted` and turn `ink-soft` on hover.

## 5. Layout Principles

- **One column**, centred, `max-w-5xl` with 16px side padding. Detail and Alerts pages narrow to `max-w-2xl`.
- **Spacing** steps in 4px (Tailwind's scale). Sections on a page are 24px apart (`gap-6`). Rows have 12px vertical
  and 16px horizontal padding.
- **Radius:** 8px (`rounded-lg`) for panels, cards and toasts; full pills (`rounded-full`) for buttons, inputs,
  selects, chips and badges *(#72)*.
- **Lists group by date.** Date headings sit above each date's panel, and Steve's Picks come first within a date.

## 6. Depth & Elevation

Flat. Depth comes from the surface steps, darkest to lightest in dark mode: `page`, `surface` / `panel`, `field`.
Hover lifts a row to `surface-hover`. The only shadows are on floating things: the Setup Alert panel and the Genre
list (`shadow-lg`), and toasts.

## 7. Do's and Don'ts

**Do**
- Use the semantic tokens for every colour.
- Pair each background with its text token (section 2).
- Keep green for actions and Steve's Picks.
- Let weight carry hierarchy.
- Check both light and dark mode.
- Keep text at WCAG AA contrast (4.5:1, or 3:1 for large text).

**Don't**
- Use Tailwind palette colours (`text-zinc-500`, `bg-amber-500`) or `dark:` colour variants in components.
- Put green text on a light background except through `link`.
- Put white text on `accent`.
- Add shadows to cards, or gradients.
- Use the source brand's name, logo or imagery.

**Mechanisms a restyle must keep:**
- Pages are static HTML, with React only where a page is interactive (ADR 0004).
- Show lists mark each date group (or Show) with `data-show-date="YYYY-MM-DD"`, and Venue and Band lists use
  `data-upcoming-shows-list` / `data-upcoming-shows` / `data-upcoming-shows-empty`, so the inline `<head>` CSS can
  hide Shows that have passed (`lib/pastShows`).
- The home page's first page carries `data-home-first-page`.
- Links that keep the Shows list's filters carry `data-keep-filters`, and the Back link `data-back` (`lib/keepFilters`).

## 8. Responsive Behaviour

- **Mobile first.** The `sm` breakpoint (640px) moves Show row details into a right-hand column, and the filter bar
  into a row of controls.
- **On phones,** each Show list item stacks: headliner, Venue · city, details, flags, calendar links. The calendar
  links are labelled buttons, easy to tap.
- **Touch targets** are at least 36px tall (`h-9` controls). Pills keep their full rounding at every size.

## 9. Agent Prompt Guide

When you build or change UI in this repo:
1. Read this file first. Use the tokens in section 2 by name (`bg-surface`, `text-ink-muted`, `text-link`,
   `bg-accent text-on-accent`, `bg-pick`…), never hex values or Tailwind palette colours.
2. If you need a colour that doesn't exist, add a token to `globals.css` (light and dark) and to the table here.
   The sync test fails until both match.
3. Lists of Shows use the Show list item (section 4). Don't introduce new card styles.
4. Check light and dark mode. For visible changes, run `npm run screenshots -- <dir>` in `frontend/` before and
   after, and put both sets in the PR.
5. Keep the mechanisms in section 7 intact. The smoke tests cover them.

Example prompt: "Add a 'Free' filter chip to the filter bar, styled as a section 4 input: a `field` pill, `ink`
text, accent focus ring. On phones it wraps under Search."
