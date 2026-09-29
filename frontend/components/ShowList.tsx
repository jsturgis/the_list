'use client'

import { useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Show } from '@/lib/types'
import ShowCard from './ShowCard'
import FilterBar from './FilterBar'
import { formatDateLong } from '@/lib/format'
import { gqlClient } from '@/lib/graphql'
import { SHOWS_QUERY } from '@/lib/queries'
import { buildFilters } from '@/lib/filters'

const PAGE_SIZE = 50

interface FilterOptions {
  regions: string[]
  ages: string[]
  genres: string[]
  dates: string[]
}

const EMPTY_FILTER_OPTIONS: FilterOptions = { regions: [], ages: [], genres: [], dates: [] }

interface ShowListProps {
  shows: Show[]
  dbTotal?: number
  filterOptions?: FilterOptions
  initialFiltersKey?: string
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

export default function ShowList({ shows: initialShows, dbTotal = 0, filterOptions = EMPTY_FILTER_OPTIONS, initialFiltersKey = '' }: ShowListProps) {
  const searchParams = useSearchParams()

  const [shows, setShows] = useState(initialShows)
  const [hasMore, setHasMore] = useState(initialShows.length >= PAGE_SIZE)
  const [loading, setLoading] = useState(false)

  const sentinelRef = useRef<HTMLDivElement>(null)
  const loadingRef = useRef(false)
  // Skip the initial no-filter fetch — SSR already gave us the first page.
  const isFirstRender = useRef(true)

  const filtersKey = searchParams.toString()
  const filters = useMemo(() => buildFilters(searchParams), [filtersKey])

  // Reset and fetch page 1 whenever filters change.
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false
      if (filtersKey === initialFiltersKey) {
        // SSR already fetched for this exact filter state — skip.
        // Reset the flag on cleanup so React Strict Mode's double-invocation
        // doesn't fall through to setShows([]) on the second run.
        return () => { isFirstRender.current = true }
      }
    }

    let cancelled = false
    loadingRef.current = true
    setLoading(true)
    setShows([])
    setHasMore(false)

    gqlClient
      .request<{ shows: Show[] }>(SHOWS_QUERY, {
        limit: PAGE_SIZE,
        offset: 0,
        ...(filters ? { filters } : {}),
      })
      .then(data => {
        if (!cancelled) {
          setShows(data.shows)
          setHasMore(data.shows.length >= PAGE_SIZE)
        }
      })
      .finally(() => {
        if (!cancelled) {
          loadingRef.current = false
          setLoading(false)
        }
      })

    return () => { cancelled = true }
  }, [filtersKey])

  // Append the next page when the sentinel comes into view.
  async function loadMore() {
    if (loadingRef.current || !hasMore) return
    loadingRef.current = true
    setLoading(true)
    try {
      const data = await gqlClient.request<{ shows: Show[] }>(SHOWS_QUERY, {
        limit: PAGE_SIZE,
        offset: shows.length,
        ...(filters ? { filters } : {}),
      })
      setShows(prev => [...prev, ...data.shows])
      setHasMore(data.shows.length >= PAGE_SIZE)
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!hasMore) return
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      entries => { if (entries[0].isIntersecting) loadMore() },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [shows.length, hasMore, filtersKey])

  const { regions, ages, genres, dates: availableDates } = filterOptions

  const picks = useMemo(() => shows.filter(s => s.isRecommended), [shows])
  const nonPicks = useMemo(
    () => picks.length > 0 ? shows.filter(s => !s.isRecommended) : shows,
    [shows, picks],
  )
  const byDate = useMemo(() => groupByDate(nonPicks), [nonPicks])
  const sortedDates = useMemo(() => Array.from(byDate.keys()).sort(), [byDate])

  return (
    <div className="flex flex-col gap-6">
      <FilterBar
        showCount={shows.length}
        dbTotal={dbTotal}
        genres={genres}
        regions={regions}
        ages={ages}
        availableDates={availableDates}
      />

      {loading && shows.length === 0 ? (
        <p className="text-center text-zinc-400 dark:text-zinc-500 py-12">Loading…</p>
      ) : shows.length === 0 ? (
        <p className="text-center text-zinc-500 py-12">No shows match your filters.</p>
      ) : (
        <>
          {picks.length > 0 && (
            <section>
              <h2 className="text-lg font-bold mb-3 text-amber-700 dark:text-amber-400">
                Steve&apos;s Picks ★
              </h2>
              <div data-testid="steves-picks" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {picks.map(show => <ShowCard key={show.id} show={show} filterQs={filtersKey} />)}
              </div>
            </section>
          )}

          <section>
            <div className="flex flex-col gap-6">
              {sortedDates.map(date => (
                <div key={date}>
                  <h3 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-2">
                    {formatDateLong(date)}
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {(byDate.get(date) ?? [])
                      .sort((a, b) => (a.doorTime ?? '').localeCompare(b.doorTime ?? ''))
                      .map(show => <ShowCard key={show.id} show={show} filterQs={filtersKey} />)}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {hasMore && (
        <div ref={sentinelRef} className="flex justify-center py-6">
          {loading && (
            <span className="text-sm text-zinc-400 dark:text-zinc-500">Loading…</span>
          )}
        </div>
      )}
    </div>
  )
}
