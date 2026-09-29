import { Suspense } from 'react'
import { gqlClient } from '@/lib/graphql'
import { SHOWS_QUERY, SHOW_COUNT_QUERY, FILTER_OPTIONS_QUERY } from '@/lib/queries'
import { buildFilters } from '@/lib/filters'
import type { Show } from '@/lib/types'

interface FilterOptions {
  regions: string[]
  ages: string[]
  genres: string[]
  dates: string[]
}
import ShowList from '@/components/ShowList'

async function fetchShows(filters?: Record<string, unknown> | null): Promise<Show[]> {
  try {
    const data = await gqlClient.request<{ shows: Show[] }>(SHOWS_QUERY, {
      limit: 50,
      offset: 0,
      ...(filters ? { filters } : {}),
    })
    return data.shows
  } catch {
    return []
  }
}

async function fetchShowCount(): Promise<number> {
  try {
    const data = await gqlClient.request<{ showCount: number }>(SHOW_COUNT_QUERY)
    return data.showCount
  } catch {
    return 0
  }
}

async function fetchFilterOptions(): Promise<FilterOptions> {
  try {
    const data = await gqlClient.request<{ filterOptions: FilterOptions }>(FILTER_OPTIONS_QUERY)
    return data.filterOptions
  } catch {
    return { regions: [], ages: [], genres: [], dates: [] }
  }
}

interface PageProps {
  searchParams: Promise<Record<string, string | string[]>>
}

export default async function Home({ searchParams }: PageProps) {
  const rawParams = await searchParams
  const urlParams = new URLSearchParams()
  for (const [key, value] of Object.entries(rawParams)) {
    if (Array.isArray(value)) {
      value.forEach(v => urlParams.append(key, v))
    } else {
      urlParams.set(key, value)
    }
  }
  const filterQs = urlParams.toString()
  const filters = buildFilters(urlParams)

  const [shows, dbTotal, filterOptions] = await Promise.all([
    fetchShows(filters),
    fetchShowCount(),
    fetchFilterOptions(),
  ])

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">This Week&apos;s Shows</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
          Upcoming Bay Area music — curated by{' '}
          <a href="mailto:skoepke@stevelist.com" className="underline hover:text-zinc-700 dark:hover:text-zinc-300">
            Steve List
          </a>.
        </p>
      </div>
      <Suspense>
        <ShowList
          shows={shows}
          dbTotal={dbTotal}
          filterOptions={filterOptions}
          initialFiltersKey={filterQs}
        />
      </Suspense>
    </div>
  )
}
