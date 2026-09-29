'use client'

import { useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Show } from '@/lib/types'
import ShowCard from './ShowCard'
import FilterBar from './FilterBar'
import { formatDateLong } from '@/lib/format'
import { gqlClient } from '@/lib/graphql'
import { SHOWS_QUERY } from '@/lib/queries'

const PAGE_SIZE = 50

interface FilterOptions {
  regions: string[]
  ages: string[]
  genres: string[]
  dates: string[]
}

interface ShowListProps {
  shows: Show[]
  dbTotal: number
  filterOptions: FilterOptions
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

function buildFilters(params: URLSearchParams): Record<string, unknown> | null {
  const f: Record<string, unknown> = {}
  const band = params.get('band'); if (band) f.bandName = band
  const venue = params.get('venue'); if (venue) f.venueName = venue
  const region = params.get('region'); if (region) f.region = region
  const fromDate = params.get('fromDate'); if (fromDate) f.fromDate = fromDate
  const toDate = params.get('toDate'); if (toDate) f.toDate = toDate
  const priceMax = params.get('priceMax'); if (priceMax) f.priceMax = parseFloat(priceMax)
  if (params.get('free') === '1') f.isFree = true
  const age = params.get('age'); if (age) f.ageRestriction = age
  const genre = params.get('genre'); if (genre) f.genre = genre
  return Object.keys(f).length > 0 ? f : null
}

export default function ShowList({ shows: initialShows, dbTotal, filterOptions }: ShowListProps) {
  const searchParams = useSearchParams()

  // Unfiltered shows — grows via infinite scroll
  const [shows, setShows] = useState(initialShows)

  // Filtered shows — fetched from backend when filters active
  const [filteredShows, setFilteredShows] = useState<Show[] | null>(null)
  const [filterLoading, setFilterLoading] = useState(false)

  // Infinite scroll
  const [scrollLoading, setScrollLoading] = useState(false)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const loadingRef = useRef(false)

  const filters = useMemo(() => buildFilters(searchParams), [searchParams.toString()])
  const hasFilters = filters !== null

  // Fetch from backend when filters change
  useEffect(() => {
    if (!filters) {
      setFilteredShows(null)
      return
    }
    let cancelled = false
    setFilterLoading(true)
    gqlClient
      .request<{ shows: Show[] }>(SHOWS_QUERY, { limit: 200, filters })
      .then(data => { if (!cancelled) setFilteredShows(data.shows) })
      .finally(() => { if (!cancelled) setFilterLoading(false) })
    return () => { cancelled = true }
  }, [searchParams.toString()])

  // Infinite scroll for unfiltered view
  async function loadMore() {
    if (loadingRef.current) return
    loadingRef.current = true
    setScrollLoading(true)
    try {
      const data = await gqlClient.request<{ shows: Show[] }>(SHOWS_QUERY, {
        limit: PAGE_SIZE,
        offset: shows.length,
      })
      setShows(prev => [...prev, ...data.shows])
    } finally {
      loadingRef.current = false
      setScrollLoading(false)
    }
  }

  useEffect(() => {
    if (hasFilters) return
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      entries => { if (entries[0].isIntersecting) loadMore() },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [shows.length, dbTotal, hasFilters])

  // Display: filtered results from backend, or unfiltered loaded set
  const displayShows = hasFilters ? (filteredShows ?? []) : shows

  const { regions, ages, genres, dates: availableDates } = filterOptions

  const picks = useMemo(() => displayShows.filter(s => s.isRecommended), [displayShows])
  const nonPicks = useMemo(
    () => picks.length > 0 ? displayShows.filter(s => !s.isRecommended) : displayShows,
    [displayShows, picks],
  )
  const byDate = useMemo(() => groupByDate(nonPicks), [nonPicks])
  const sortedDates = useMemo(() => Array.from(byDate.keys()).sort(), [byDate])

  const showCount = hasFilters ? (filteredShows?.length ?? 0) : shows.length

  return (
    <div className="flex flex-col gap-6">
      <FilterBar
        showCount={showCount}
        totalCount={shows.length}
        dbTotal={dbTotal}
        genres={genres}
        regions={regions}
        ages={ages}
        availableDates={availableDates}
      />

      {filterLoading ? (
        <p className="text-center text-zinc-400 dark:text-zinc-500 py-12">Loading…</p>
      ) : displayShows.length === 0 ? (
        <p className="text-center text-zinc-500 py-12">No shows match your filters.</p>
      ) : (
        <>
          {picks.length > 0 && (
            <section>
              <h2 className="text-lg font-bold mb-3 text-amber-700 dark:text-amber-400">
                Steve&apos;s Picks ★
              </h2>
              <div data-testid="steves-picks" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {picks.map(show => <ShowCard key={show.id} show={show} />)}
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
                      .map(show => <ShowCard key={show.id} show={show} />)}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {!hasFilters && shows.length < dbTotal && (
        <div ref={sentinelRef} className="flex justify-center py-6">
          {scrollLoading && (
            <span className="text-sm text-zinc-400 dark:text-zinc-500">Loading…</span>
          )}
        </div>
      )}
    </div>
  )
}
