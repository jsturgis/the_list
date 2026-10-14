import type { APIRoute } from 'astro'
import { href } from '@/lib/basePath'

// Points crawlers to the sitemap (@astrojs/sitemap). Crawlers only read it at the domain root: the custom domain.
export const GET: APIRoute = ({ site }) =>
  new Response(`User-agent: *\nAllow: /\n\nSitemap: ${new URL(href('/sitemap-index.xml'), site)}\n`)
