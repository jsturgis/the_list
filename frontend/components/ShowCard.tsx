'use client'

import Link from 'next/link'
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

function StatusBadge({ status, compact }: { status: Show['status']; compact?: boolean }) {
  if (status !== 'cancelled' && status !== 'postponed') return null
  const isCancelled = status === 'cancelled'
  return (
    <span
      className={`${compact ? 'text-[10px] px-1.5' : 'text-xs px-2'} font-bold uppercase tracking-wide py-0.5 rounded w-fit shrink-0 ${
        isCancelled
          ? 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
          : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400'
      }`}
    >
      {isCancelled ? 'Cancelled' : 'Postponed'}
    </span>
  )
}

function Flags({ show, compact }: { show: Show; compact?: boolean }) {
  if (!(show.willSellOut || show.isPit || show.isDrinkTickets || show.isNoReentry)) return null
  const size = compact ? 'text-[11px] px-1 py-px' : 'px-1.5 py-0.5'
  const neutral = 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300'
  return (
    <div className={`flex flex-wrap gap-1 ${compact ? 'sm:flex-nowrap' : 'text-xs'}`}>
      {show.willSellOut && (
        <span className={`${size} rounded bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400`}>
          Will Sell Out
        </span>
      )}
      {show.isPit && <span className={`${size} rounded ${neutral}`}>Pit Warning</span>}
      {show.isDrinkTickets && <span className={`${size} rounded ${neutral}`}>Drink Tickets</span>}
      {show.isNoReentry && <span className={`${size} rounded ${neutral}`}>No Re-entry</span>}
    </div>
  )
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
          <StatusBadge status={show.status} compact />
          <p className="truncate text-sm">
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
            {show.venue.city}
          </div>
        )}

        <div className="flex flex-wrap sm:flex-nowrap items-center gap-x-2 gap-y-1 whitespace-nowrap text-xs text-zinc-500 dark:text-zinc-400 sm:shrink-0">
          {meta && <span>{meta}</span>}
          <Flags show={show} compact />
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

      {showVenue && (
        <div className="text-sm text-zinc-600 dark:text-zinc-300">
          {show.venue.name}
          {' · '}
          {show.venue.city}
        </div>
      )}

      <div className="flex flex-wrap gap-2 text-xs text-zinc-500 dark:text-zinc-400">
        {door && <span>{door}</span>}
        {price && <span>{price}</span>}
        {age && <span>{age}</span>}
      </div>

      <Flags show={show} />
    </Link>
  )
}
