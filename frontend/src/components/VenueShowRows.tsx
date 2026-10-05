import ShowCard from './ShowCard'
import { useBayAreaToday } from '@/lib/useBayAreaToday'
import { formatDateLong } from '@/lib/format'
import type { ShowSummary } from '@/lib/types'

/**
 * A Venue's Upcoming Shows as compact rows grouped by date. Pages are built weekly, so dates before
 * today (Bay Area time) are hidden in the browser.
 */
export default function VenueShowRows({ shows }: { shows: ShowSummary[] }) {
  const today = useBayAreaToday()

  const visible = today ? shows.filter(s => s.date >= today) : shows
  if (visible.length === 0) {
    return <p className="text-sm text-ink-muted">No upcoming shows.</p>
  }

  const byDate = new Map<string, ShowSummary[]>()
  for (const s of visible) byDate.set(s.date, [...(byDate.get(s.date) ?? []), s])

  return (
    <section aria-labelledby="venue-upcoming-shows">
      <h2 id="venue-upcoming-shows" className="text-base font-semibold mb-3 text-ink">
        Upcoming Shows
      </h2>
      <div className="flex flex-col gap-6">
        {Array.from(byDate.keys()).sort().map(date => (
          <div key={date}>
            <h3 className="text-sm font-semibold text-ink-muted uppercase tracking-wide mb-2">
              {formatDateLong(date)}
            </h3>
            <div className="flex flex-col divide-y divide-line-subtle rounded-lg border border-line-subtle bg-surface overflow-hidden">
              {(byDate.get(date) ?? [])
                .slice()
                .sort((a, b) => (a.doorTime ?? '').localeCompare(b.doorTime ?? ''))
                .map(show => <ShowCard key={show.id} show={show} layout="row" showVenue={false} />)}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
