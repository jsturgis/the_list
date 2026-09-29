'use client'

import { useRouter, useSearchParams, usePathname } from 'next/navigation'
import { useCallback } from 'react'

const REGIONS = [
  { value: '', label: 'All Regions' },
  { value: 'sf', label: 'SF' },
  { value: 'east_bay', label: 'East Bay' },
  { value: 'north_bay', label: 'North Bay' },
  { value: 'south_bay', label: 'South Bay' },
  { value: 'santa_cruz', label: 'Santa Cruz' },
]

const AGE_OPTIONS = [
  { value: '', label: 'Any Age' },
  { value: 'a/a', label: 'All Ages' },
  { value: '18+', label: '18+' },
  { value: '21+', label: '21+' },
]

interface FilterBarProps {
  showCount: number
  totalCount: number
}

export default function FilterBar({ showCount, totalCount }: FilterBarProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const update = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString())
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

  const hasFilters =
    searchParams.has('region') ||
    searchParams.has('band') ||
    searchParams.has('priceMax') ||
    searchParams.has('free') ||
    searchParams.has('age')

  return (
    <div className="flex flex-col gap-3 p-4 bg-zinc-50 dark:bg-zinc-900 rounded-lg border border-zinc-200 dark:border-zinc-700">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
          {showCount === totalCount ? (
            <>{totalCount} shows</>
          ) : (
            <>
              {showCount} of {totalCount} shows
            </>
          )}
        </p>
        {hasFilters && (
          <button
            onClick={clearAll}
            className="text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 underline"
          >
            Clear filters
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-region" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Region
          </label>
          <select
            id="filter-region"
            value={searchParams.get('region') ?? ''}
            onChange={e => update('region', e.target.value)}
            className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100"
          >
            {REGIONS.map(r => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="filter-band" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Band name
          </label>
          <input
            id="filter-band"
            type="text"
            placeholder="Search by band…"
            value={searchParams.get('band') ?? ''}
            onChange={e => update('band', e.target.value)}
            className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400"
          />
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
            className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400"
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
            className="rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 py-1.5 text-zinc-900 dark:text-zinc-100"
          >
            {AGE_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2 pt-5">
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
    </div>
  )
}
