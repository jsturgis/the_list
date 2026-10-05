import { defineConfig } from 'astro/config'
import react from '@astrojs/react'
import tailwindcss from '@tailwindcss/vite'

// The Deploy workflow passes the base path and URL GitHub Pages reports (actions/configure-pages): "" and
// https://list.sturgis.me with the custom domain, "/the_list" and https://jsturgis.github.io/the_list
// without it. Local builds and tests default to /the_list.
const base = process.env.PAGES_BASE_PATH ?? '/the_list'
const site = process.env.PAGES_SITE_URL || `https://jsturgis.github.io${base}`

export default defineConfig({
  // A static site (ADR 0002): every page is built ahead of time from the export in export/ (not published).
  output: 'static',
  base: base || '/',
  site,
  // Every page is a directory index (bands/10/index.html), so refreshing any URL loads it.
  trailingSlash: 'always',
  build: { format: 'directory' },
  integrations: [react()],
  vite: { plugins: [tailwindcss()] },
  // localhost:3000/the_list/alerts/** is on Supabase's sign-in redirect allow-list (ADR 0003).
  server: { port: 3000 },
})
