import type { Show, Venue } from '@/lib/types'
import ShowCard from './ShowCard'
import { formatDateLong, mapsHref, telHref } from '@/lib/format'

const REGION_LABELS: Record<string, string> = {
  sf: 'SF',
  east_bay: 'East Bay',
  north_bay: 'North Bay',
  south_bay: 'South Bay',
  santa_cruz: 'Santa Cruz',
}

function groupByDate(shows: Show[]): Map<string, Show[]> {
  const map = new Map<string, Show[]>()
  for (const show of shows) {
    const existing = map.get(show.date) ?? []
    existing.push(show)
    map.set(show.date, existing)
  }
  return map
}

interface VenueDetailProps {
  venue: Venue
  upcomingShows: Show[]
}

export default function VenueDetail({ venue, upcomingShows }: VenueDetailProps) {
  const byDate = groupByDate(upcomingShows)
  const sortedDates = Array.from(byDate.keys()).sort()

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      <header>
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-50">{venue.name}</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
          {venue.city}
          {venue.region && REGION_LABELS[venue.region] ? ` · ${REGION_LABELS[venue.region]}` : ''}
        </p>
      </header>

      {(venue.websiteUrl || venue.wikipediaUrl || venue.phone || venue.googleRating || venue.address) && (
        <section className="flex flex-col gap-2 text-sm text-zinc-600 dark:text-zinc-300">
          {venue.address && (
            <a
              href={mapsHref(venue)}
              target="_blank"
              rel="noopener noreferrer"
              className="w-fit hover:underline"
            >
              {venue.address}
            </a>
          )}
          {venue.phone && (
            <a href={telHref(venue.phone)} className="w-fit hover:underline">
              {venue.phone}
            </a>
          )}
          {venue.googleRating && (
            <p>Google rating: {venue.googleRating.toFixed(1)} ★</p>
          )}
          <div className="flex flex-wrap gap-3 mt-1">
            {venue.websiteUrl && (
              <a
                href={venue.websiteUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm px-3 py-1.5 rounded bg-zinc-800 text-white hover:bg-zinc-700 dark:bg-zinc-700 dark:hover:bg-zinc-600"
              >
                Website ↗
              </a>
            )}
            {venue.wikipediaUrl && (
              <a
                href={venue.wikipediaUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm px-3 py-1.5 rounded bg-zinc-100 text-zinc-800 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              >
                Wikipedia ↗
              </a>
            )}
          </div>
        </section>
      )}

      {venue.description && (
        <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
          {venue.description}
        </p>
      )}

      {upcomingShows.length > 0 ? (
        <section>
          <h2 className="text-base font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
            Upcoming Shows
          </h2>
          <div className="flex flex-col gap-6">
            {sortedDates.map(date => (
              <div key={date}>
                <h3 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-2">
                  {formatDateLong(date)}
                </h3>
                <div className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden">
                  {(byDate.get(date) ?? [])
                    .sort((a, b) => (a.doorTime ?? '').localeCompare(b.doorTime ?? ''))
                    .map(show => (
                      <ShowCard key={show.id} show={show} layout="row" showVenue={false} />
                    ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No upcoming shows.</p>
      )}
    </article>
  )
}
