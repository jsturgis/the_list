/**
 * Which links the Admin page takes: TicketWeb event pages (backend/app/ingestion/ticketweb.py reads them).
 *
 * The page checks links as they're typed; the admin Edge Function checks them again with the same rules, in
 * supabase/functions/_shared/eventUrls.ts (Deno can't import from the Astro tree). eventUrls.test.ts checks the two
 * agree.
 */

export type UrlCheck = { ok: true; url: string; provider: 'ticketweb' } | { ok: false; reason: string }

/** A TicketWeb event page, without the tracking a link from elsewhere carries; or why it isn't one. */
export function checkEventUrl(text: string): UrlCheck {
  let url: URL
  try {
    url = new URL(text.trim())
  } catch {
    return { ok: false, reason: "isn't a link" }
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return { ok: false, reason: "isn't a web link" }
  const host = url.hostname.toLowerCase()
  if (host === 'bandsintown.com' || host.endsWith('.bandsintown.com')) {
    return { ok: false, reason: 'Bandsintown blocks automated reads: add a screenshot of the event instead' }
  }
  if (host !== 'ticketweb.com' && !host.endsWith('.ticketweb.com')) {
    return { ok: false, reason: "isn't a TicketWeb link (add a screenshot of other events)" }
  }
  if (!/^\/event\/[^/]+/.test(url.pathname)) return { ok: false, reason: "isn't a TicketWeb event page" }
  return { ok: true, url: `https://${host}${url.pathname}`, provider: 'ticketweb' }
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
