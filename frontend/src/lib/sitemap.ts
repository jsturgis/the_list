/**
 * Whether a built page belongs in the sitemap (@astrojs/sitemap's filter): not the noindex ones, the Unsubscribe and
 * Admin pages, and the numeric Band, Venue and Show URLs (/bands/12/), which redirect to the pages at their slugs.
 */
export function inSitemap(page: string): boolean {
  const path = new URL(page).pathname
  return !path.endsWith('/alerts/unsubscribe/') && !path.endsWith('/admin/') && !/\/(bands|venues|shows)\/\d+\/$/.test(path)
}
