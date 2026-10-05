/**
 * CSS that hides Shows dated before today (Bay Area time) on a page built from an export made on `from`. CSS can't
 * compare dates, so it's one selector per day from `from` up to yesterday: a few, as the site is rebuilt weekly.
 *
 * Lists mark each Show, or each date's group of Shows, with data-show-date="YYYY-MM-DD". A list marked
 * data-upcoming-shows-list with none left is hidden too, and the data-upcoming-shows-empty message in its
 * data-upcoming-shows container, if there is one, is shown instead.
 *
 * The layout inlines this function's source into each page's <head>, so the rules apply before anything is drawn.
 * It must stay self-contained: no imports, and nothing from outside its own body.
 */
export function pastShowsStyle(from: string, now: Date = new Date()): string {
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now)
  const day = new Date(`${from}T12:00:00Z`)
  if (Number.isNaN(day.getTime())) return ''

  const past: string[] = []
  // At most about a year of days; a site that hasn't been rebuilt for longer has bigger problems.
  while (past.length < 400) {
    const date = day.toISOString().slice(0, 10)
    if (date >= today) break
    past.push(`[data-show-date="${date}"]`)
    day.setUTCDate(day.getUTCDate() + 1)
  }
  if (past.length === 0) return ''

  const passed = past.join(', ')
  const current = `[data-show-date]:not(${passed})`
  return [
    `${passed} { display: none !important; }`,
    `[data-upcoming-shows-list]:not(:has(${current})) { display: none !important; }`,
    `[data-upcoming-shows]:not(:has(${current})) [data-upcoming-shows-empty] { display: block !important; }`,
  ].join('\n')
}
