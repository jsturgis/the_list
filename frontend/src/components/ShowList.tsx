import { useEffect, useMemo, useRef, useState } from 'react'
import type { HomeShow } from '@/lib/types'
import { ArrowPathIcon, MagnifyingGlassIcon } from '@heroicons/react/20/solid'
import ShowCard from './ShowCard'
import FilterBar from './FilterBar'
import { formatDateLong } from '@/lib/format'
import { useQuery } from '@/lib/navigation'

/** Shows rendered at a time; more appear as the list scrolls. The home page's HTML has the first page. */
export const PAGE_SIZE = 50

interface FilterOptions {
  regions: string[]
  ages: string[]
  genres: string[]
  dates: string[]
}

const EMPTY_FILTER_OPTIONS: FilterOptions = { regions: [], ages: [], genres: [], dates: [] }

interface ShowListProps {
  /** Shows to list, already in date order; null while they load. */
  shows: HomeShow[] | null
  /** "Showing N": defaults to the number of Shows. */
  showCount?: number
  dbTotal?: number
  filterOptions?: FilterOptions
  /**
   * The list is the page's build-time first page: its dates are marked, so the page's CSS hides any that have
   * passed (lib/pastShows), and it's held back while the URL has a query (the layout's <head> script), as it's
   * unfiltered.
   */
  firstPage?: boolean
}

/** Groups shows by date, with Steve's Picks first within each date. */
function groupByDate(shows: HomeShow[]): Map<string, HomeShow[]> {
  const map = new Map<string, HomeShow[]>()
  for (const show of shows) {
    const existing = map.get(show.date) ?? []
    existing.push(show)
    map.set(show.date, existing)
  }
  for (const group of map.values()) {
    group.sort((a, b) => Number(b.isRecommended) - Number(a.isRecommended))
  }
  return map
}

const NO_SHOWS: HomeShow[] = []

export default function ShowList({ shows: listed, showCount, dbTotal = 0, filterOptions = EMPTY_FILTER_OPTIONS, firstPage = false }: ShowListProps) {
  const filtersKey = useQuery().toString()
  const shows = listed ?? NO_SHOWS
  const [visible, setVisible] = useState(PAGE_SIZE)
  const sentinelRef = useRef<HTMLDivElement>(null)

  // Start from the first page whenever the list itself changes.
  const [prevShows, setPrevShows] = useState(shows)
  if (shows !== prevShows) {
    setPrevShows(shows)
    setVisible(PAGE_SIZE)
  }

  const hasMore = visible < shows.length
  const byDate = useMemo(() => groupByDate(shows.slice(0, visible)), [shows, visible])
  const sortedDates = useMemo(() => Array.from(byDate.keys()).sort(), [byDate])

  // Reveal the next page when the sentinel scrolls into view.
  useEffect(() => {
    if (!hasMore) return
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      entries => { if (entries[0].isIntersecting) setVisible(v => v + PAGE_SIZE) },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasMore, visible])

  const { regions, ages, genres, dates: availableDates } = filterOptions

  return (
    <div className="flex flex-col gap-6">
      <FilterBar
        showCount={listed ? (showCount ?? shows.length) : null}
        dbTotal={dbTotal}
        genres={genres}
        regions={regions}
        ages={ages}
        availableDates={availableDates}
      />

      {!listed ? (
        <p className="flex items-center justify-center gap-1.5 text-ink-faint py-12">
          <ArrowPathIcon className="size-4 shrink-0 animate-spin" />
          Loading…
        </p>
      ) : shows.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-12 text-ink-muted">
          <MagnifyingGlassIcon className="size-6 text-ink-faint" />
          <p>No shows match your filters.</p>
        </div>
      ) : (
        <>
          <section data-home-first-page={firstPage ? '' : undefined}>
            <div className="flex flex-col gap-6">
              {sortedDates.map(date => (
                <div key={date} data-show-date={firstPage ? date : undefined}>
                  <h3 className="text-sm font-semibold text-ink-muted uppercase tracking-wide mb-2">
                    {formatDateLong(date)}
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {(byDate.get(date) ?? []).map(show => <ShowCard key={show.id} show={show} filterQs={filtersKey} />)}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {hasMore && <div ref={sentinelRef} className="py-6" aria-hidden="true" />}
    </div>
  )
}
