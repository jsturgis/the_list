import { href } from '@/lib/basePath'
import { formatDateShort } from '@/lib/format'
import type { Show } from '@/lib/types'

/**
 * A Band's Upcoming Shows, linking to each Show. Static: pages are built weekly, so lib/upcomingShows hides
 * dates before today (Bay Area time) in the browser, and the whole section when none are left.
 */
export default function BandShows({ shows }: { shows: Show[] }) {
  if (shows.length === 0) return null

  return (
    <section data-upcoming-shows="">
      <h2 className="text-base font-semibold mb-3 text-ink">
        Upcoming Shows
      </h2>
      <ul className="flex flex-col gap-2">
        {shows.map(show => (
          <li key={show.id} data-show-date={show.date}>
            <a
              href={href(`/shows/${show.id}/`)}
              className="flex items-center justify-between gap-4 text-sm -mx-2 px-2 py-1 rounded hover:bg-muted"
            >
              <span className="font-medium text-ink min-w-0 truncate">
                {show.venue.name}
                {' · '}
                {show.venue.city}
              </span>
              <span className="text-ink-muted shrink-0">
                {formatDateShort(show.date)}
              </span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
