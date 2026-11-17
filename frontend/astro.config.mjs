import { defineConfig } from 'astro/config'
import react from '@astrojs/react'
import { unified } from '@astrojs/markdown-remark'
import sitemap from '@astrojs/sitemap'
import starlight from '@astrojs/starlight'
import tailwindcss from '@tailwindcss/vite'
import remarkDocs, { GUIDES } from './src/lib/docsMarkdown'
import { inSitemap } from './src/lib/sitemap'

// The Deploy workflow passes the base path and URL GitHub Pages reports (actions/configure-pages): "" and
// https://list.sturgis.me with the custom domain, "/the_list" and https://jsturgis.github.io/the_list
// without it. Local builds and tests default to /the_list.
const base = process.env.PAGES_BASE_PATH ?? '/the_list'
const site = process.env.PAGES_SITE_URL || `https://jsturgis.github.io${base}`

/** An Expressive Code plugin: gives each code block's <pre> a tabindex, so the keyboard can scroll it. */
function focusableCodeBlocks() {
  const visit = node => {
    if (node.type === 'element' && node.tagName === 'pre') node.properties = { ...node.properties, tabIndex: 0 }
    for (const child of node.children ?? []) visit(child)
  }
  return { name: 'focusable-code-blocks', hooks: { postprocessRenderedBlock: ({ renderData }) => visit(renderData.blockAst) } }
}

export default defineConfig({
  // A static site (ADR 0002): every page is built ahead of time from the export in export/ (not published).
  output: 'static',
  base: base || '/',
  site,
  // Every page is a directory index (bands/10/index.html), so refreshing any URL loads it.
  trailingSlash: 'always',
  build: { format: 'directory' },
  // sitemap-index.xml lists the pages for search engines (robots.txt points to it), not the noindex ones.
  integrations: [
    // The docs, at /docs/ (ADR 0005): Starlight renders the Markdown guides in ../docs/guide/ (src/content.config.ts)
    // with a sidebar, search and a table of contents, in the site's colours (src/styles/starlight.css). Every other
    // page is this project's own (src/pages), and keeps its own 404.
    starlight({
      title: 'The List',
      description: 'How The List is built, run and deployed.',
      favicon: '/favicon.png',
      disable404Route: true,
      credits: false,
      customCss: ['@fontsource-variable/figtree', './src/styles/starlight.css'],
      social: [{ icon: 'github', label: 'The List on GitHub', href: 'https://github.com/jsturgis/the_list' }],
      // Guides live outside this project, so their paths start with "../": the URL resolves to docs/guide/<file>.
      editLink: { baseUrl: 'https://github.com/jsturgis/the_list/edit/main/frontend/' },
      sidebar: [
        { label: 'Docs', link: '/docs/' },
        {
          label: 'Guides',
          items: GUIDES.map(name => `docs/${name}`),
        },
        { label: 'Back to the Shows', link: '/' },
      ],
      // Code blocks scroll sideways when a line is long, and a scrolling region must take keyboard focus.
      // They sit in the site's surface panels (8px radius, flat) rather than the highlighter's own background.
      expressiveCode: {
        plugins: [focusableCodeBlocks()],
        styleOverrides: {
          borderRadius: '0.5rem',
          borderColor: 'var(--line)',
          codeBackground: 'var(--surface)',
          frames: {
            frameBoxShadowCssValue: 'none',
            terminalBackground: 'var(--surface)',
            terminalTitlebarBackground: 'var(--surface)',
            terminalTitlebarBorderBottomColor: 'var(--line)',
            editorBackground: 'var(--surface)',
            editorTabBarBackground: 'var(--surface)',
            editorActiveTabBackground: 'var(--surface)',
          },
        },
      },
      components: {
        // The docs follow the system's light/dark setting, like the rest of the site: no switch.
        ThemeSelect: './src/components/docs/ThemeSelect.astro',
        // Draws the guides' diagrams.
        MarkdownContent: './src/components/docs/MarkdownContent.astro',
      },
    }),
    react(),
    sitemap({ filter: inSitemap }),
  ],
  // The guides link to each other by file name and hold Mermaid diagrams, as GitHub reads them (lib/docsMarkdown).
  markdown: { processor: unified({ remarkPlugins: [remarkDocs] }) },
  // The dev server may read ../docs/guide/, outside this project.
  vite: { plugins: [tailwindcss()], server: { fs: { allow: ['..'] } } },
  // localhost:3000/the_list/alerts/** is on Supabase's sign-in redirect allow-list (ADR 0003).
  server: { port: 3000 },
})
