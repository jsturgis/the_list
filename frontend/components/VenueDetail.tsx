import type { Show, Venue } from '@/lib/types'
import VenueShowRows from './VenueShowRows'
import { mapsHref, telHref } from '@/lib/format'

const REGION_LABELS: Record<string, string> = {
  sf: 'SF',
  east_bay: 'East Bay',
  north_bay: 'North Bay',
  south_bay: 'South Bay',
  santa_cruz: 'Santa Cruz',
}

const AGE_POLICY: Record<string, string> = { all_ages: 'All ages', varies: 'Varies by show' }

/** "@catalystclub" -> "https://www.instagram.com/catalystclub/" */
function instagramUrl(handle: string): string {
  return `https://www.instagram.com/${handle.replace(/^@/, '')}/`
}

interface VenueDetailProps {
  venue: Venue
  upcomingShows: Show[]
}

export default function VenueDetail({ venue, upcomingShows }: VenueDetailProps) {
  const rules = [
    venue.isSoberSpace && 'Sober space',
    venue.isCashOnly && 'Cash only',
    venue.membershipRequired && 'Membership required',
  ].filter((r): r is string => Boolean(r))
  const agePolicy = venue.defaultAgeRestriction
    ? AGE_POLICY[venue.defaultAgeRestriction] ?? venue.defaultAgeRestriction
    : null

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      {venue.imageUrl && (
        // Hosts vary (and the site is a static export), so a plain <img> rather than next/image.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={venue.imageUrl} alt={venue.name} className="w-full max-h-72 object-cover rounded-lg" />
      )}
      <header>
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-50">{venue.name}</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
          {venue.neighborhood ? `${venue.neighborhood} · ` : ''}
          {venue.city}
          {venue.region && REGION_LABELS[venue.region] ? ` · ${REGION_LABELS[venue.region]}` : ''}
        </p>
        {rules.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {rules.map(rule => (
              <span key={rule} className="text-xs px-2 py-0.5 rounded bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                {rule}
              </span>
            ))}
          </div>
        )}
      </header>

      {(venue.nearestTransit || venue.instagram || agePolicy) && (
        <section className="flex flex-col gap-1 text-sm text-zinc-600 dark:text-zinc-300">
          {agePolicy && <p>Usual ages: {agePolicy}</p>}
          {venue.nearestTransit && <p>Transit: {venue.nearestTransit}</p>}
          {venue.instagram && (
            <a href={instagramUrl(venue.instagram)} target="_blank" rel="noopener noreferrer" className="w-fit hover:underline">
              {venue.instagram}
            </a>
          )}
        </section>
      )}

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

      <VenueShowRows shows={upcomingShows} />
    </article>
  )
}
