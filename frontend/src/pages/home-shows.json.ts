import type { APIRoute } from 'astro'
import { siteData } from '@/lib/siteData.server'

/** The home page's Shows, trimmed to what its list, filters and search use; the browser loads it after the first page. */
export const GET: APIRoute = () => Response.json(siteData().homeShows())
