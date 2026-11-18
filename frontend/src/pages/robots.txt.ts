import type { APIRoute } from 'astro'
import { href } from '@/lib/basePath'

// Points crawlers to the sitemap (@astrojs/sitemap). Crawlers only read it at the domain root: the custom domain.
// The .ics files are kept out of search: GitHub Pages can't send an X-Robots-Tag header, so they're disallowed here
// and their links are rel="nofollow".
export const GET: APIRoute = ({ site }) =>
  new Response(
    `User-agent: *\nAllow: /\nDisallow: ${href('/calendar/')}\n\nSitemap: ${new URL(href('/sitemap-index.xml'), site)}\n`,
  )
