# Starlight for the docs

The docs at `/docs/` are rendered by [Starlight](https://starlight.astro.build/), Astro's documentation framework, instead of the site's own pages. They began as two hand-written Astro pages that rendered the Markdown guides in `docs/guide/` into the site's shell. That gave a list of guides and a page each, but nothing a reader expects of documentation: no sidebar, no search, no table of contents, no previous and next. Building those ourselves would have meant owning a docs framework.

Starlight runs inside the existing Astro project as an integration, so the docs are still part of the one static site (ADR 0002) and the one build and deploy. The guides stay where they were, as plain Markdown that GitHub also renders: a content collection loads `docs/guide/*.md` and puts each at `/docs/<file name>/`, so no URL changed.

## Considered Options

- **Keep the hand-written pages**: no dependency, and the docs share the site's shell exactly. But every docs feature is ours to build and test.
- **Starlight**: the same framework as the site, one build, and the docs' standard furniture for free. Chosen.
- **Docusaurus, MkDocs Material or VitePress**: all widely used, but each is a second site with its own toolchain (React, Python or Vue), a second build in the Deploy workflow, and a second theme to match to the site's.

## Consequences

- **The docs have Starlight's layout, not the site's shell.** They don't use `Layout`, `PageHeader` or `Section`, and the layout-consistency tests don't cover them. They match the site through a theme, `src/styles/starlight.css`, which sets Starlight's colour variables from the site's tokens and its font to Figtree (DESIGN.md, "Docs pages"). The tokens moved to their own file, `src/styles/tokens.css`, so both stylesheets can import them without the docs loading Tailwind.
- **No light/dark switch.** Starlight's theme picker is replaced by an empty component: the docs follow the system's setting, like every other page.
- **The guides are still written for GitHub too.** They link to each other by file name and hold diagrams as Mermaid code blocks. A remark plugin (`src/lib/docsMarkdown.ts`) rewrites those links to the guides' pages and turns each Mermaid block into a region that `src/lib/diagrams.ts` draws, in the theme's colours. Starlight's own Markdown extras (asides, tabs, MDX components) would not render on GitHub, so the guides don't use them.
- **The sidebar is a list in `docsMarkdown.ts` (`GUIDES`).** A new guide needs adding there; a test fails until it is.
- **Markdown is processed by `unified`** (`@astrojs/markdown-remark`) rather than Astro 7's default processor, because Starlight and the remark plugin need it. Only the guides are Markdown.
- **Search is Pagefind**, built into Starlight: the build writes a static index (about 700 KB, loaded only when someone searches). It covers the docs pages only, not Shows, Bands or Venues.
- **Starlight catches every URL the site's own pages don't**, so its 404 page is turned off (`disable404Route`) and the site's own `404.astro` still answers.
- **Starlight is pre-1.0.** It's pinned to an exact version, and an upgrade may need changes to the theme mapping or the two replaced components (`src/components/docs/`).
