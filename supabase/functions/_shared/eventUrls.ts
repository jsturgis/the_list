/**
 * Which links the Admin page takes: any event page on the web, as a link to read (backend/app/ingestion/
 * event_page.py). A site that turns the read away makes the job fail with a request for a screenshot instead.
 *
 * The same rules are in frontend/src/lib/eventUrls.ts, for the page to check links as they're typed; Deno can't
 * import from the Astro tree. frontend/__tests__/eventUrls.test.ts checks the two agree.
 */
export type UrlCheck = { ok: true; url: string; provider: 'ticketweb' | 'page' } | { ok: false; reason: string }

/** Longest link taken (the ingest_jobs table holds up to 2000 characters). */
const MAX_URL = 2000

/**
 * An event's page on any site, or why the text isn't one. A TicketWeb link loses the tracking a link from
 * elsewhere carries (its own reader, backend/app/ingestion/ticketweb.py); any other site's keeps its query, which
 * may say which event it is (backend/app/ingestion/event_page.py). Only the fragment goes.
 */
export function checkEventUrl(text: string): UrlCheck {
  let url: URL
  try {
    url = new URL(text.trim())
  } catch {
    return { ok: false, reason: "isn't a link" }
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return { ok: false, reason: "isn't a web link" }
  const host = url.hostname.toLowerCase()
  if (!host.includes('.') || host === 'localhost' || /^[\d.]+$/.test(host) || host.startsWith('[')) {
    return { ok: false, reason: "isn't a public website" }
  }
  if (host === 'ticketweb.com' || host.endsWith('.ticketweb.com')) {
    return { ok: true, url: `https://${host}${url.pathname}`, provider: 'ticketweb' }
  }
  url.hash = ''
  if (url.href.length > MAX_URL) return { ok: false, reason: 'is too long' }
  return { ok: true, url: url.href, provider: 'page' }
}

/** The screenshots the Admin page takes, and how big they may be (the storage bucket enforces the same). */
export const SCREENSHOT_TYPES = ['image/png', 'image/jpeg', 'image/webp']
export const SCREENSHOT_MAX_BYTES = 10 * 1024 * 1024

/** Whether a person may use the Admin page: "admin" among the permissions in their app_metadata, which only the
 * project's secret key can set (supabase/migrations/0004_ingest_jobs.sql). */
export function isAdmin(appMetadata: Record<string, unknown> | undefined | null): boolean {
  const permissions = appMetadata?.permissions
  return Array.isArray(permissions) && permissions.includes('admin')
}
