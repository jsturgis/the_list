'use client'

import { useSearchParams } from 'next/navigation'
import { useMemo } from 'react'
import type { Show } from '@/lib/types'
import ShowCard from './ShowCard'
import FilterBar from './FilterBar'

interface ShowListProps {
  shows: Show[]
}

function applyFilters(shows: Show[], params: URLSearchParams): Show[] {
  let result = shows

  const region = params.get('region')
  if (region) {
    result = result.filter(s => s.venue.region === region)
  }

  const band = params.get('band')
  if (band) {
    const lower = band.toLowerCase()
    result = result.filter(s =>
      s.acts.some(a => a.band.name.toLowerCase().includes(lower)),
    )
  }

  const priceMax = params.get('priceMax')
  if (priceMax !== null && priceMax !== '') {
    const max = parseFloat(priceMax)
    if (!isNaN(max)) {
      result = result.filter(s => s.priceMin !== null && s.priceMin <= max)
    }
  }

  if (params.get('free') === '1') {
    result = result.filter(s => s.isFree)
  }

  const age = params.get('age')
  if (age) {
    result = result.filter(s => s.ageRestriction === age)
  }

  const genre = params.get('genre')
  if (genre) {
    result = result.filter(s =>
      s.acts.some(a => a.band.genres.includes(genre)),
    )
  }

  return result
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

function formatDateHeading(dateStr: string): string {
  const d = new Date(dateStr + 'T12:00:00')
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
}

export default function ShowList({ shows }: ShowListProps) {
  const searchParams = useSearchParams()

  const picks = useMemo(() => shows.filter(s => s.isRecommended), [shows])

  const genres = useMemo(() => {
    const set = new Set<string>()
    for (const show of shows) {
      for (const act of show.acts) {
        for (const genre of act.band.genres) {
          set.add(genre)
        }
      }
    }
    return Array.from(set).sort()
  }, [shows])

  const filtered = useMemo(() => applyFilters(shows, searchParams), [shows, searchParams])

  const filteredPicks = useMemo(
    () => picks.filter(s => filtered.some(f => f.id === s.id)),
    [picks, filtered],
  )

  const nonPickFiltered = useMemo(
    () => filteredPicks.length > 0 ? filtered.filter(s => !s.isRecommended) : filtered,
    [filtered, filteredPicks],
  )

  const byDate = useMemo(() => groupByDate(nonPickFiltered), [nonPickFiltered])
  const sortedDates = useMemo(
    () => Array.from(byDate.keys()).sort(),
    [byDate],
  )

  return (
    <div className="flex flex-col gap-6">
      <FilterBar showCount={filtered.length} totalCount={shows.length} genres={genres} />

      {filteredPicks.length > 0 && (
        <section>
          <h2 className="text-lg font-bold mb-3 text-amber-700 dark:text-amber-400">
            Steve&apos;s Picks ★
          </h2>
          <div
            data-testid="steves-picks"
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
          >
            {filteredPicks.map(show => (
              <ShowCard key={show.id} show={show} />
            ))}
          </div>
        </section>
      )}

      {filtered.length === 0 ? (
        <p className="text-center text-zinc-500 py-12">No shows match your filters.</p>
      ) : (
        <section>
          <div className="flex flex-col gap-6">
            {sortedDates.map(date => (
              <div key={date}>
                <h3 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-2">
                  {formatDateHeading(date)}
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {(byDate.get(date) ?? [])
                    .sort((a, b) => (a.doorTime ?? '').localeCompare(b.doorTime ?? ''))
                    .map(show => (
                      <ShowCard key={show.id} show={show} />
                    ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
