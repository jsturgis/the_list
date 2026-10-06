import Section from './Section'
import ShowRow from './ShowRow'
import type { Show } from '@/lib/types'

/**
 * A Venue's Upcoming Shows as one list of Show rows, each starting with its compact date. Pages are built weekly,
 * so the page's CSS hides Shows dated before today (Bay Area time), and shows "No upcoming shows." when none are
 * left (lib/pastShows).
 */
export default function VenueShowRows({ shows }: { shows: Show[] }) {
  const sorted = shows.slice().sort((a, b) => a.date.localeCompare(b.date) || (a.doorTime ?? '').localeCompare(b.doorTime ?? ''))
  return (
    <div data-upcoming-shows="">
      {shows.length > 0 && (
        <Section title="Upcoming Shows" headingId="venue-upcoming-shows" plain data-upcoming-shows-list="">
          <ul className="flex flex-col divide-y divide-line-subtle overflow-hidden rounded-lg bg-surface">
            {sorted.map(show => (
              // The date on the list item, so the page's CSS hides the whole item once it has passed.
              <li key={show.id} data-show-date={show.date}><ShowRow show={show} showVenue={false} showDate /></li>
            ))}
          </ul>
        </Section>
      )}
      {/* Shown by the page's CSS too, when every Show listed has passed (lib/pastShows). */}
      <p className="text-sm text-ink-muted" data-upcoming-shows-empty="" style={shows.length > 0 ? { display: 'none' } : undefined}>
        No upcoming shows.
      </p>
    </div>
  )
}
