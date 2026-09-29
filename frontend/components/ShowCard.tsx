'use client'

import Link from 'next/link'
import type { Show } from '@/lib/types'
import { formatTime, formatPrice } from '@/lib/format'

function formatAge(age: string): string {
  if (age === 'a/a') return 'All Ages'
  return age
}

interface ShowCardProps {
  show: Show
  filterQs?: string
}

export default function ShowCard({ show, filterQs = '' }: ShowCardProps) {
  const showHref = filterQs ? `/shows/${show.id}?${filterQs}` : `/shows/${show.id}`
  const venueHref = filterQs ? `/venues/${show.venue.id}?${filterQs}` : `/venues/${show.venue.id}`
  const headliner = show.acts[0]?.band
  const supports = show.acts.slice(1)
  const price = formatPrice(show.priceMin, show.priceMax, show.isFree) ?? ''
  const door = formatTime(show.doorTime)
  const age = formatAge(show.ageRestriction)
  const isCancelled = show.status === 'cancelled'
  const isPostponed = show.status === 'postponed'

  return (
    <Link
      href={showHref}
      className={`rounded-lg border p-4 flex flex-col gap-2 transition-all hover:shadow-md hover:brightness-[0.97] dark:hover:brightness-110 outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${
        show.isRecommended
          ? 'border-amber-400 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-600'
          : 'border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900'
      }`}
      data-recommended={show.isRecommended ? '' : undefined}
    >
      {(isCancelled || isPostponed) && (
        <div
          className={`text-xs font-bold uppercase tracking-wide px-2 py-0.5 rounded w-fit ${
            isCancelled
              ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
              : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400'
          }`}
        >
          {isCancelled ? 'Cancelled' : 'Postponed'}
        </div>
      )}

      {headliner && (
        <h3 className="font-semibold text-base leading-tight text-zinc-900 dark:text-zinc-50">
          {headliner.name}
        </h3>
      )}

      {supports.length > 0 && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {supports.map(a => a.band.name).join(', ')}
        </p>
      )}

      <div className="text-sm text-zinc-600 dark:text-zinc-300">
        <span
          className="hover:underline"
          onClick={e => { e.preventDefault(); window.location.href = venueHref }}
        >
          {show.venue.name}
        </span>
        {' · '}
        {show.venue.city}
      </div>

      <div className="flex flex-wrap gap-2 text-xs text-zinc-500 dark:text-zinc-400">
        {door && <span>{door}</span>}
        {price && <span>{price}</span>}
        {age && <span>{age}</span>}
      </div>

      {(show.willSellOut || show.isPit || show.isDrinkTickets || show.isNoReentry) && (
        <div className="flex flex-wrap gap-1 text-xs">
          {show.willSellOut && (
            <span className="px-1.5 py-0.5 rounded bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400">
              Will Sell Out
            </span>
          )}
          {show.isPit && (
            <span className="px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              Pit Warning
            </span>
          )}
          {show.isDrinkTickets && (
            <span className="px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              Drink Tickets
            </span>
          )}
          {show.isNoReentry && (
            <span className="px-1.5 py-0.5 rounded bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              No Re-entry
            </span>
          )}
        </div>
      )}
    </Link>
  )
}
