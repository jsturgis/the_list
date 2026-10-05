import Section from './Section'
import ShowRow from './ShowRow'
import { formatDateLong } from '@/lib/format'
import type { Show } from '@/lib/types'

/**
 * A Venue's Upcoming Shows as compact rows grouped by date. Pages are built weekly, so the page's CSS hides dates
 * before today (Bay Area time), and shows "No upcoming shows." when none are left (lib/pastShows).
 */
export default function VenueShowRows({ shows }: { shows: Show[] }) {
  const byDate = new Map<string, Show[]>()
  for (const s of shows) byDate.set(s.date, [...(byDate.get(s.date) ?? []), s])

  return (
    <div data-upcoming-shows="">
      {shows.length > 0 && (
        <Section title="Upcoming Shows" headingId="venue-upcoming-shows" plain data-upcoming-shows-list="">
          <div className="flex flex-col gap-6">
            {Array.from(byDate.keys()).sort().map(date => (
              <div key={date} data-show-date={date}>
                <h3 className="text-xl font-bold text-ink mb-2">
                  {formatDateLong(date)}
                </h3>
                <div className="flex flex-col divide-y divide-line-subtle overflow-hidden rounded-lg bg-surface">
                  {(byDate.get(date) ?? [])
                    .slice()
                    .sort((a, b) => (a.doorTime ?? '').localeCompare(b.doorTime ?? ''))
                    .map(show => <ShowRow key={show.id} show={show} showVenue={false} headingLevel={4} />)}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}
      {/* Shown by the page's CSS too, when every Show listed has passed (lib/pastShows). */}
      <p className="text-sm text-ink-muted" data-upcoming-shows-empty="" style={shows.length > 0 ? { display: 'none' } : undefined}>
        No upcoming shows.
      </p>
    </div>
  )
}
