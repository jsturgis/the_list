import { href } from '@/lib/basePath'
import { formatDateShort } from '@/lib/format'
import type { ShowSummary } from '@/lib/types'
import { useBayAreaToday } from '@/lib/useBayAreaToday'

/**
 * A Band's Upcoming Shows, linking to each Show. Pages are built weekly, so dates before today (Bay Area time)
 * are hidden in the browser; nothing renders when none are left.
 */
export default function BandShows({ shows }: { shows: ShowSummary[] }) {
  const today = useBayAreaToday()
  const visible = today ? shows.filter(s => s.date >= today) : shows
  if (visible.length === 0) return null

  return (
    <section>
      <h2 className="text-base font-semibold mb-3 text-ink">
        Upcoming Shows
      </h2>
      <ul className="flex flex-col gap-2">
        {visible.map(show => (
          <li key={show.id}>
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
