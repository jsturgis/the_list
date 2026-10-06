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
| `ink-faint` | Decorative icons, icon buttons and placeholders (3:1); never text | `#808080` | `#7c7c7c` |
| **Lines** | | | |
| `line` | Borders | `#e2e2e2` | `#2a2a2a` |
| `line-subtle` | Dividers between rows, the header rule | `#ececec` | `#222222` |
| `line-strong` | Strong borders (form fields) | `#cfcfcf` | `#4d4d4d` |
| `focus-ring` | The keyboard focus outline, and a focused Show row's ring (3:1 on every background) | `#117a37` | `#1ed760` |
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
| `danger` | Cancelled, Sold out, errors | `red-700` | `red-400` |
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
hues, so people recognise them, one shade darker (`green-700`, `orange-700`, `teal-700`) so their white labels pass
WCAG AA.

## 3. Typography Rules

- **Typeface:** **Figtree** (variable, SIL Open Font License), self-hosted through `@fontsource-variable/figtree`
  and preloaded by the layout. Fallback: `ui-sans-serif, system-ui, sans-serif`. Tailwind's `font-sans` is Figtree.
  There's no second family and no monospace in the UI.
- **Weights:** 800 for page titles; 700 for headings, headliners and button labels; 400 for everything else. Use
  600 sparingly.

| Role | Size | Weight | Notes |
|---|---|---|---|
| Page title (`h1`) | 36px (`text-4xl`); 30px (`text-3xl`) on phones | 800 | tracking −0.02em (global); every page, through `PageHeader` |
| Page subtitle | 18px (`text-lg`) | 400 | `ink-soft`, under the h1; an optional eyebrow above it is 14px `ink-muted` |
| Section heading (`h2`: Lineup, Venue, Details, Upcoming Shows, Similar Bands…) | 24px (`text-2xl`) | 700 | through `Section` |
| Date heading on the home page (`h2`) | 24px (`text-2xl`) | 700 | sentence case, `ink` |
| Date heading inside a section (`h3`, a Venue's or Band's Upcoming Shows) | 20px (`text-xl`) | 700 | |
| Lineup headliner | 20px (`text-xl`) | 700 | supports below at 16px |
| Headliner in a Show row | 16px | 700 | `ink`; supports follow in `ink-muted`, prefixed "with"; a heading one level below the date |
| Body | 16px / 14px (`text-sm`) | 400 | |
| Meta: time · price · age, captions | 12–14px (`text-xs`/`text-sm`) | 400 | `ink-muted` or `ink-soft` |
| Badges (flags, statuses) | 12px | 600 | statuses uppercase |
| Button labels | as the button | 700 | UPPERCASE, tracking 0.1em (global for `<button>`) |

## 4. Component Stylings

- **Buttons**
  - *Primary:* `bg-accent` / `text-on-accent`, pill (`rounded-full`), uppercase label. One per view, for
    the main action (Email me a sign-in link, Save).
  - *Neutral:* `bg-strong` / `text-on-inverse`.
  - *Outline:* `border-accent`, `text-link` on `surface` (Setup Alert).
  - *Quiet:* text-only in `ink-muted`, with an underline or a `muted` hover (Clear filters, Back).
- **Inputs and selects:** `bg-field`, pill-shaped (`rounded-full`, `px-3`), `line-strong` border, `ink` text,
  `ink-faint` placeholders. Checkboxes keep the browser's shape, tinted with `accent-accent`.
  A form's only field (the Alerts page's Email) can go without a visible label: its placeholder names it, and
  `aria-label` gives it the same accessible name.
- **Focus:** keyboard focus is a 2px `focus-ring` outline, offset 2px, on everything (a global rule; don't remove
  it with `outline-none` unless something else shows focus). Show rows ring the whole row in `focus-ring` instead.
  `focus-ring` is the text-safe green, because the accent itself is under 3:1 on light backgrounds.
- **Filter bar:** a `panel` block (8px radius) above the list, holding the Shows count, the Region, Search and
  Genre controls, Free only, Advanced filters and Setup Alert.
- **Show list item:**
  - Shows are listed as rows (`ShowRow`), not cards, in one `surface` panel per date (8px radius) with
    `line-subtle` dividers. Venue pages use the same row without the Venue line; Band pages use it with the Venue line.
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
  - Badges are small pills (`rounded-full`) that never wrap inside; a row of them wraps badge by badge.
- **Page header (`PageHeader`):** every page starts with one: an optional eyebrow (a Show's status and date), the
  h1, an optional subtitle (`text-lg ink-soft`) and an optional row of chips.
- **Sections (`Section`):** a `<section aria-labelledby>`: a 24px bold `h2` on the page, then the content in a
  panel below it (`surface`, 8px radius, 20px padding), 12px apart. The heading, and an optional note at the right
  end of its line in `text-sm ink-muted` ("3 of 20 alerts"), are never inside the panel. `plain` drops the panel
  for content that already sits in panels (date-grouped Show rows).
- **Key facts (`FactList`):** a `<dl>` grid, three columns from `sm` and one per line on phones. Each fact has an
  icon and a `text-xs ink-muted` label, over a `text-base font-semibold ink` value (Doors, Price, Ages).
- **Actions (`ActionLinks`):** a wrapping row of pill links, 14px bold: primary (`bg-accent text-on-accent`, at
  most one: Tickets), secondary (outline `line-strong`, `ink`), or brand colours for the
  streaming services. External ones carry an outward-arrow icon.
- **Detail pages (Show, Venue, Band):** in order: Back, `PageHeader`, key facts, actions, then `Section`s. A Show
  has Lineup, Venue and Notes; a Venue has Details, About and Upcoming Shows; a Band has Upcoming Shows and
  Similar Bands. Upcoming Shows on Venue and Band pages use the Show list item, grouped under 20px date headings.
- **Loading (`Ghost`):** anything waiting on Supabase (who's signed in, their alerts and weekly email setting, an
  unsubscribe) shows ghost placeholders: `line`-coloured bars in the shape of the content to come, pulsing
  (`motion-safe:animate-pulse`, so still for reduced motion). Headings that are already known stay real. Ghosts are
  `aria-hidden`; a visually hidden "Loading …" label stands in for screen readers. Static data (Shows, Bands,
  Venues) is in the page and never needs one.
- **Banners:** `accent-soft` with `accent-soft-line` and `accent-soft-ink` (special events).
- **Toasts:** `inverse` with `on-inverse`, 8px radius, at the bottom of the screen.
- **Links:** links inside running text (a sentence) are `text-link underline underline-offset-2`, always
  underlined, so colour isn't the only cue. Standalone links (rows, lists, the Venue name, facts) are underlined
  on hover only. Navigation links (header, Back) are `ink-muted` and turn `ink-soft` on hover.

## 5. Layout Principles

- **Two widths, set by the layout** (`Layout`'s `width` prop), never by a page's components:
  - *wide:* the home page, the full `max-w-5xl` (1024px) with 16px side padding, for the filter bar and list.
  - *narrow (the default):* every other page (Show, Venue, Band, Alerts, Unsubscribe, 404) in one centred 672px
    column (`max-w-2xl`, `w-full`). The Back link sits above it at the full-width left edge (the layout's `back`
    slot), lined up with the home page's content.
- **Spacing** steps in 4px (Tailwind's scale). Blocks on a page (header, facts, sections) are 24px apart (`gap-6`). Rows have 12px vertical
  and 16px horizontal padding.
- **Radius:** 8px (`rounded-lg`) for panels, cards and toasts; full pills (`rounded-full`) for buttons, inputs,
  selects, chips, badges and small icon buttons. Hover backgrounds on list links (Similar Bands, a Band's Upcoming
  Shows) and floating lists (the Genre options) are 8px.
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
- **On phones,** each Show list item stacks: headliner, Venue · city, details, flags, calendar links. The Setup
  Alert panel spans the filter bar's full width instead of hanging off the button. The calendar
  links are labelled buttons, easy to tap.
- **Touch targets** are at least 36px tall (`h-9` controls). Pills keep their full rounding at every size.

## 9. Agent Prompt Guide

When you build or change UI in this repo:
1. Read this file first. Use the tokens in section 2 by name (`bg-surface`, `text-ink-muted`, `text-link`,
   `bg-accent text-on-accent`, `bg-pick`…), never hex values or Tailwind palette colours.
2. If you need a colour that doesn't exist, add a token to `globals.css` (light and dark) and to the table here.
   The sync test fails until both match. If you pair tokens in a new way (text on a background), add the pair to
   `frontend/__tests__/contrast.test.ts`, which checks every listed pair against WCAG AA in both modes.
3. Lists of Shows use the Show list item (section 4). Don't introduce new card styles.
4. Check light and dark mode. For visible changes, run `npm run screenshots -- <dir>` in `frontend/` before and
   after, and put both sets in the PR.
5. Keep the mechanisms in section 7 intact. The smoke tests cover them, and the axe checks (`e2e/a11y.spec.ts`)
   fail on serious or critical accessibility violations, including contrast, in both modes.
6. **Every page** follows the same shell (`e2e/consistency.spec.ts` checks the first three):
   - it uses the layout's width (narrow unless it's the Shows list), with no `max-w-*` of its own
   - it opens with `PageHeader`, so its h1 matches every other page's (the 404 is centred, with a music-note
     icon, but uses the same h1 and subtitle sizes)
   - its sections are `Section`s, so their `h2`s match
   - links in sentences are underlined; actions are `ActionLinks` pills, with at most one primary

Example prompt: "Add a 'Free' filter chip to the filter bar, styled as a section 4 input: a `field` pill, `ink`
text, accent focus ring. On phones it wraps under Search."
