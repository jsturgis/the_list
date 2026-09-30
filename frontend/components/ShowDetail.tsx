import Link from 'next/link'
import type { Show } from '@/lib/types'
import { formatTime, formatPrice, formatDateLongYear, mapsHref } from '@/lib/format'
import VenueLink from './VenueLink'

function formatAge(age: string): string {
  if (age === 'a/a') return 'All Ages'
  return age
}

interface ShowDetailProps {
  show: Show
}

export default function ShowDetail({ show }: ShowDetailProps) {
  const isCancelled = show.status === 'cancelled'
  const isPostponed = show.status === 'postponed'
  const door = formatTime(show.doorTime)
  const set = formatTime(show.setTime)
  const price = formatPrice(show.priceMin, show.priceMax, show.isFree) ?? 'TBA'
  const age = formatAge(show.ageRestriction)

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      {(isCancelled || isPostponed) && (
        <div
          className={`text-sm font-bold uppercase tracking-wide px-3 py-1.5 rounded w-fit ${
            isCancelled
              ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
              : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400'
          }`}
        >
          {isCancelled ? 'Cancelled' : 'Postponed'}
        </div>
      )}

      <header>
        {show.specialEvent && (
          <p className="text-sm font-medium text-amber-700 dark:text-amber-400 mb-1">{show.specialEvent}</p>
        )}
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-1">{formatDateLongYear(show.date)}</p>
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-50">
          {show.acts[0]?.band.name ?? 'Unknown'}
        </h1>
        <p className="text-lg text-zinc-600 dark:text-zinc-300 mt-1">
          at <VenueLink venueId={show.venue.id} className="hover:underline">{show.venue.name}</VenueLink> · {show.venue.city}
        </p>
      </header>

      <section className="flex flex-wrap gap-4 text-sm text-zinc-600 dark:text-zinc-300">
        {door && (
          <div>
            <span className="font-medium">Doors: </span>
            {door}
            {set && <> / Set: {set}</>}
          </div>
        )}
        <div>
          <span className="font-medium">Price: </span>
          {price}
        </div>
        <div>
          <span className="font-medium">Ages: </span>
          {age}
        </div>
        {show.ticketProvider && <div>Tickets via {show.ticketProvider}</div>}
      </section>

      {(show.isSoldOut || show.isMatinee || show.isBenefit || show.willSellOut || show.isPit ||
        show.isDrinkTickets || show.isNoReentry) && (
        <section className="flex flex-wrap gap-2">
          {show.isSoldOut && (
            <span className="px-2 py-1 rounded text-sm font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">
              Sold out
            </span>
          )}
          {show.isMatinee && (
            <span className="px-2 py-1 rounded text-sm bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-400">
              Matinee
            </span>
          )}
          {show.isBenefit && (
            <span className="px-2 py-1 rounded text-sm bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
              {show.benefitCause ? `Benefit: ${show.benefitCause}` : 'Benefit'}
            </span>
          )}
          {show.willSellOut && (
            <span className="px-2 py-1 rounded text-sm bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400">
              Will Sell Out
            </span>
          )}
          {show.isPit && (
            <span className="px-2 py-1 rounded text-sm bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              Pit Warning
            </span>
          )}
          {show.isDrinkTickets && (
            <span className="px-2 py-1 rounded text-sm bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              Drink Tickets
            </span>
          )}
          {show.isNoReentry && (
            <span className="px-2 py-1 rounded text-sm bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              No Re-entry
            </span>
          )}
        </section>
      )}

      <section>
        <h2 className="text-base font-semibold mb-3 text-zinc-900 dark:text-zinc-100">Lineup</h2>
        <ol className="flex flex-col gap-2">
          {show.acts
            .slice()
            .sort((a, b) => a.position - b.position)
            .map(act => (
              <li key={act.band.id}>
                <Link
                  href={`/bands/${act.band.id}`}
                  className={`${act.position === 0 ? 'font-bold' : 'font-normal'} hover:underline text-zinc-900 dark:text-zinc-50`}
                >
                  <span data-testid="act-name">{act.band.name}</span>
                </Link>
              </li>
            ))}
        </ol>
      </section>

      <section>
        <h2 className="text-base font-semibold mb-3 text-zinc-900 dark:text-zinc-100">Venue</h2>
        <div className="flex flex-col gap-1 text-sm text-zinc-600 dark:text-zinc-300">
          <VenueLink venueId={show.venue.id} className="font-medium text-zinc-900 dark:text-zinc-100 hover:underline">{show.venue.name}</VenueLink>
          {show.venue.address && (
            <a
              href={mapsHref(show.venue)}
              target="_blank"
              rel="noopener noreferrer"
              className="w-fit hover:underline"
            >
              {show.venue.address}
            </a>
          )}
          {show.venue.websiteUrl && (
            <a
              href={show.venue.websiteUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-amber-600 hover:underline dark:text-amber-400"
            >
              Venue website ↗
            </a>
          )}
          {show.venue.description && (
            <p className="mt-2 text-zinc-500 dark:text-zinc-400 italic">{show.venue.description}</p>
          )}
        </div>
      </section>

      {show.notes && (
        <section>
          <h2 className="text-base font-semibold mb-1 text-zinc-900 dark:text-zinc-100">Notes</h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-300">{show.notes}</p>
        </section>
      )}
    </article>
  )
}
