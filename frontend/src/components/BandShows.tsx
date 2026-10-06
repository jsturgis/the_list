import Section from './Section'
import ShowRow from './ShowRow'
import type { Show } from '@/lib/types'

/**
 * A Band's Upcoming Shows as one list of Show rows, each starting with its compact date. Pages are built weekly, so
 * the page's CSS hides rows dated before today (Bay Area time), and the whole section when none are left
 * (lib/pastShows).
 */
export default function BandShows({ shows }: { shows: Show[] }) {
  if (shows.length === 0) return null
  const sorted = shows.slice().sort((a, b) => a.date.localeCompare(b.date) || (a.doorTime ?? '').localeCompare(b.doorTime ?? ''))
  return (
    <Section title="Upcoming Shows" headingId="band-upcoming-shows" plain data-upcoming-shows-list="">
      <ul className="flex flex-col divide-y divide-line-subtle overflow-hidden rounded-lg bg-surface">
        {sorted.map(show => (
          // The date on the list item, so the page's CSS hides the whole item once it has passed.
          <li key={show.id} data-show-date={show.date}><ShowRow show={show} showDate /></li>
        ))}
      </ul>
    </Section>
  )
}
