import ShowCard from './ShowCard'
import { formatDateLong } from '@/lib/format'
import type { Show } from '@/lib/types'

/**
 * A Venue's Upcoming Shows as compact rows grouped by date. Static: pages are built weekly, so lib/upcomingShows
 * hides dates before today (Bay Area time) in the browser, and shows "No upcoming shows." when none are left.
 */
export default function VenueShowRows({ shows }: { shows: Show[] }) {
  const byDate = new Map<string, Show[]>()
  for (const s of shows) byDate.set(s.date, [...(byDate.get(s.date) ?? []), s])

  return (
    <div data-upcoming-shows="">
      {shows.length > 0 && (
        <section aria-labelledby="venue-upcoming-shows" data-upcoming-shows-list="">
          <h2 id="venue-upcoming-shows" className="text-base font-semibold mb-3 text-ink">
            Upcoming Shows
          </h2>
          <div className="flex flex-col gap-6">
            {Array.from(byDate.keys()).sort().map(date => (
              <div key={date} data-show-date={date}>
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
      )}
      <p className="text-sm text-ink-muted" data-upcoming-shows-empty="" hidden={shows.length > 0}>
        No upcoming shows.
      </p>
    </div>
  )
}
