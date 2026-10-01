'use client'

import Link from 'next/link'
import { ClockIcon, MapPinIcon, StarIcon, TicketIcon, UserIcon } from '@heroicons/react/16/solid'
import { Flags, StatusBadge } from './ShowBadges'
import type { Show } from '@/lib/types'
import { formatTime, formatPrice } from '@/lib/format'

function formatAge(age: string): string {
  if (age === 'a/a') return 'All Ages'
  return age
}

export type ShowCardLayout = 'card' | 'row'

interface ShowCardProps {
  show: Show
  filterQs?: string
  /** 'card' for the grid (default); 'row' for a compact single-line list item. */
  layout?: ShowCardLayout
  /** Hide venue name/city, e.g. when already on that Venue's page. */
  showVenue?: boolean
}

/** "Western Addition, San Francisco" when the neighborhood is known, else the city. */
function venueLocation(show: Show): string {
  return show.venue.neighborhood ? `${show.venue.neighborhood}, ${show.venue.city}` : show.venue.city
}

export default function ShowCard({ show, filterQs = '', layout = 'card', showVenue = true }: ShowCardProps) {
  const showHref = filterQs ? `/shows/${show.id}?${filterQs}` : `/shows/${show.id}`
  const headliner = show.acts[0]?.band
  const supports = show.acts.slice(1)
  const price = formatPrice(show.priceMin, show.priceMax, show.isFree) ?? ''
  const door = formatTime(show.doorTime)
  const age = formatAge(show.ageRestriction)
  const meta = [door, price, age].filter(Boolean).join(' · ')
  const focus = 'outline-none focus-visible:ring-2 focus-visible:ring-amber-500'

  if (layout === 'row') {
    return (
      <Link
        href={showHref}
        className={`flex flex-col sm:flex-row sm:items-center gap-x-4 gap-y-1 px-4 py-3 border-l-2 transition-colors ${focus} ${
          show.isRecommended
            ? 'border-amber-400 bg-amber-50 hover:bg-amber-100 dark:border-amber-600 dark:bg-amber-950/20 dark:hover:bg-amber-950/40'
            : 'border-transparent hover:bg-zinc-50 dark:hover:bg-zinc-800/60'
        }`}
        data-recommended={show.isRecommended ? '' : undefined}
        data-layout="row"
      >
        <div className="flex items-center gap-2 min-w-0 sm:flex-1">
          <StatusBadge status={show.status} size="compact" />
          <p className="truncate text-sm">
            {show.isRecommended && <span className="sr-only">Steve&apos;s pick</span>}
            {headliner && (
              <span className="font-semibold text-zinc-900 dark:text-zinc-50">{headliner.name}</span>
            )}
            {supports.length > 0 && (
              <span className="text-zinc-500 dark:text-zinc-400">
                {headliner && ', '}
                {supports.map(a => a.band.name).join(', ')}
              </span>
            )}
          </p>
        </div>

        {showVenue && (
          <div className="text-sm text-zinc-600 dark:text-zinc-300 truncate sm:w-56 sm:shrink-0">
            {show.venue.name}
            {' · '}
            {venueLocation(show)}
          </div>
        )}

        <div className="flex flex-wrap sm:flex-nowrap items-center gap-x-2 gap-y-1 whitespace-nowrap text-xs text-zinc-500 dark:text-zinc-400 sm:shrink-0">
          {meta && <span>{meta}</span>}
          <Flags show={show} size="compact" />
        </div>
      </Link>
    )
  }

  return (
    <Link
      href={showHref}
      className={`rounded-lg border p-4 flex flex-col gap-2 transition-all hover:shadow-md hover:brightness-[0.97] dark:hover:brightness-110 ${focus} ${
        show.isRecommended
          ? 'border-amber-400 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-600'
          : 'border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-900'
      }`}
      data-recommended={show.isRecommended ? '' : undefined}
    >
      <StatusBadge status={show.status} />

      {(headliner || show.isRecommended) && (
        <div className="flex items-start gap-1.5">
          {show.isRecommended && (
            <>
              <StarIcon className="size-4 mt-0.5 shrink-0 text-amber-500 dark:text-amber-400" />
              <span className="sr-only">Steve&apos;s pick</span>
            </>
          )}
          {headliner && (
            <h3 className="font-semibold text-base leading-tight text-zinc-900 dark:text-zinc-50">
              {headliner.name}
            </h3>
          )}
        </div>
      )}

      {supports.length > 0 && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {supports.map(a => a.band.name).join(', ')}
        </p>
      )}

      {showVenue && (
        <div className="flex items-start gap-1 text-sm text-zinc-600 dark:text-zinc-300">
          <MapPinIcon className="size-3.5 mt-0.5 shrink-0 text-zinc-400 dark:text-zinc-500" />
          <span>
            {show.venue.name}
            {' · '}
            {venueLocation(show)}
          </span>
        </div>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
        {door && <span className="inline-flex items-center gap-1"><ClockIcon className="size-3.5 shrink-0" />{door}</span>}
        {price && <span className="inline-flex items-center gap-1"><TicketIcon className="size-3.5 shrink-0" />{price}</span>}
        {age && <span className="inline-flex items-center gap-1"><UserIcon className="size-3.5 shrink-0" />{age}</span>}
      </div>

      <Flags show={show} size="card" />
    </Link>
  )
}
