import Section from './Section'
import ShowRow from './ShowRow'
import { formatDateLong } from '@/lib/format'
import type { Show } from '@/lib/types'

/**
 * A Band's Upcoming Shows as Show rows grouped by date, like the home and Venue pages. Pages are built weekly, so
 * the page's CSS hides dates before today (Bay Area time), and the whole section when none are left (lib/pastShows).
 */
export default function BandShows({ shows }: { shows: Show[] }) {
  if (shows.length === 0) return null
  const byDate = new Map<string, Show[]>()
  for (const s of shows) byDate.set(s.date, [...(byDate.get(s.date) ?? []), s])

  return (
    <Section title="Upcoming Shows" headingId="band-upcoming-shows" plain data-upcoming-shows-list="">
      <div className="flex flex-col gap-6">
        {Array.from(byDate.keys()).sort().map(date => (
          <div key={date} data-show-date={date}>
            <h3 className="text-xl font-bold text-ink mb-2">{formatDateLong(date)}</h3>
            <div className="flex flex-col divide-y divide-line-subtle overflow-hidden rounded-lg bg-surface">
              {(byDate.get(date) ?? []).map(show => <ShowRow key={show.id} show={show} headingLevel={4} />)}
            </div>
          </div>
        ))}
      </div>
    </Section>
  )
}
