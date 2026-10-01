'use client'

import { useRouter, useSearchParams, usePathname } from 'next/navigation'
import { ChevronRightIcon, InformationCircleIcon, MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/16/solid'
import { useCallback, useEffect, useRef, useState } from 'react'
import Combobox from './Combobox'
import { LEGACY_SEARCH_PARAMS, searchParam } from '@/lib/filters'

const REGION_LABELS: Record<string, string> = {
  sf: 'SF',
  east_bay: 'East Bay',
  north_bay: 'North Bay',
  south_bay: 'South Bay',
  santa_cruz: 'Santa Cruz',
}

function ageLabel(age: string): string {
  return age === 'a/a' ? 'All Ages' : age
}


interface FilterBarProps {
  showCount: number
  dbTotal: number
  genres: string[]
  regions: string[]
  ages: string[]
  availableDates: string[]
}

export default function FilterBar({ showCount, dbTotal, genres, regions, ages, availableDates }: FilterBarProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const update = useCallback(
    (key: string, value: string, replaces: string[] = []) => {
      const params = new URLSearchParams(searchParams.toString())
      replaces.forEach(k => params.delete(k))
      if (value) {
        params.set(key, value)
      } else {
        params.delete(key)
      }
      router.replace(`${pathname}?${params.toString()}`, { scroll: false })
    },
    [router, pathname, searchParams],
  )

  const clearAll = useCallback(() => {
    router.replace(pathname, { scroll: false })
  }, [router, pathname])

  // Local state for the search input so every keystroke doesn't round-trip
  // through router.replace (which is async and causes characters to drop).
  const [searchInput, setSearchInput] = useState(searchParam(searchParams))

  // Track the last value we sent to the URL. The sync effect below checks
  // this so it doesn't overwrite local state with a stale URL update that
  // WE triggered — only genuine external changes (e.g. Clear filters) sync.
  const lastSentSearch = useRef(searchParam(searchParams))

  useEffect(() => {
    const urlSearch = searchParam(searchParams)
    if (urlSearch !== lastSentSearch.current) {
      setSearchInput(urlSearch)
      lastSentSearch.current = urlSearch
    }
  }, [searchParams])

  // Keep a stable ref to `update` so the debounce effect depends only on
  // input state, not on searchParams changing via other filters.
  const updateRef = useRef(update)
  useEffect(() => {
    updateRef.current = update
  }, [update])

  useEffect(() => {
    const timer = setTimeout(() => {
      lastSentSearch.current = searchInput
      updateRef.current('q', searchInput, LEGACY_SEARCH_PARAMS)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  const hasAdvancedFilters =
    searchParams.has('fromDate') ||
    searchParams.has('toDate') ||
    searchParams.has('priceMax') ||
    searchParams.has('age')

  const [showAdvanced, setShowAdvanced] = useState(hasAdvancedFilters)

  const hasFilters =
    searchParams.has('fromDate') ||
    searchParams.has('toDate') ||
    searchParams.has('region') ||
    searchParams.has('q') ||
    searchParams.has('priceMax') ||
    searchParams.has('free') ||
    searchParams.has('age') ||
    searchParams.has('genre')

  return (
    <div className="flex flex-col gap-3 p-4 bg-zinc-50 dark:bg-zinc-900 rounded-lg border border-zinc-200 dark:border-zinc-700">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          Showing {showCount} of {dbTotal} shows
        </p>
        {hasFilters && (
          <button
            onClick={clearAll}
            className="inline-flex items-center gap-0.5 text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 underline"
          >
            <XMarkIcon className="size-3.5 shrink-0" />
            Clear filters
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[1fr_1.5fr_1fr_auto] gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-region" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Region
          </label>
          <select
            id="filter-region"
            value={searchParams.get('region') ?? ''}
            onChange={e => update('region', e.target.value)}
            className="h-9 rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100"
          >
            <option value="">All Regions</option>
            {regions.map(r => (
              <option key={r} value={r}>
                {REGION_LABELS[r] ?? r}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="filter-search" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Band or venue
          </label>
          <div className="relative">
            <MagnifyingGlassIcon className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-zinc-400" />
            <input
              id="filter-search"
              type="text"
              placeholder="Search bands & venues…"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              className="h-9 w-full rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm pl-8 pr-2 py-1.5 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="filter-genre" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Genre
          </label>
          <Combobox
            id="filter-genre"
            options={genres}
            value={searchParams.get('genre') ?? ''}
            onChange={g => update('genre', g)}
            placeholder="Any genre…"
            aria-describedby={searchParams.get('genre') ? 'filter-genre-note' : undefined}
          />
          {searchParams.get('genre') && (
            <p id="filter-genre-note" role="note" className="flex items-start gap-1 text-xs text-amber-700 dark:text-amber-400">
              <InformationCircleIcon className="size-3.5 mt-px shrink-0" />
              Not every artist has genre info yet, so shows where no artist has a known genre are hidden.
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 self-start h-9 mt-5">
          <input
            id="filter-free"
            type="checkbox"
            checked={searchParams.get('free') === '1'}
            onChange={e => update('free', e.target.checked ? '1' : '')}
            className="rounded border-zinc-300 text-amber-500"
          />
          <label htmlFor="filter-free" className="text-sm text-zinc-700 dark:text-zinc-300">
            Free only
          </label>
        </div>
      </div>

      <div>
        <button
          onClick={() => setShowAdvanced(v => !v)}
          className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
        >
          <ChevronRightIcon className={`size-3.5 transition-transform ${showAdvanced ? 'rotate-90' : ''}`} />
          Advanced filters
          {hasAdvancedFilters && !showAdvanced && (
            <span className="ml-1 px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400 text-[10px] font-medium">active</span>
          )}
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="filter-from-date" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                From date
              </label>
              <input
                id="filter-from-date"
                type="date"
                value={searchParams.get('fromDate') ?? ''}
                min={availableDates[0] ?? ''}
                max={searchParams.get('toDate') || availableDates[availableDates.length - 1] || ''}
                onChange={e => update('fromDate', e.target.value)}
                className="h-9 rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="filter-to-date" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                To date
              </label>
              <input
                id="filter-to-date"
                type="date"
                value={searchParams.get('toDate') ?? ''}
                min={searchParams.get('fromDate') || availableDates[0] || ''}
                max={availableDates[availableDates.length - 1] ?? ''}
                onChange={e => update('toDate', e.target.value)}
                className="h-9 rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="filter-age" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                Age restriction
              </label>
              <select
                id="filter-age"
                value={searchParams.get('age') ?? ''}
                onChange={e => update('age', e.target.value)}
                className="h-9 rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100"
              >
                <option value="">Any Age</option>
                {ages.map(a => (
                  <option key={a} value={a}>
                    {ageLabel(a)}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="filter-price" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                Max price ($)
              </label>
              <input
                id="filter-price"
                type="number"
                min={0}
                placeholder="e.g. 20"
                value={searchParams.get('priceMax') ?? ''}
                onChange={e => update('priceMax', e.target.value)}
                className="h-9 rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
