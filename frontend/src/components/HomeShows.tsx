import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { ExclamationTriangleIcon } from '@heroicons/react/20/solid'
import ShowList from './ShowList'
import { loadHomeShows } from '@/lib/data'
import { filterShows } from '@/lib/filterShows'
import { buildFilters } from '@/lib/filters'
import { useQuery } from '@/lib/navigation'
import type { HomePage, HomeShow } from '@/lib/types'

const noSubscription = () => () => {}

/**
 * Home page body: the Shows matching the URL's filters. The page's HTML has the build's first page (`page`), so
 * Shows are on screen before any data loads; the browser then loads every Show (home-shows.json) and filters them.
 */
export default function HomeShows({ page }: { page: HomePage }) {
  const filtersKey = useQuery().toString()
  // False while prerendering and hydrating, so the first browser render matches the build's HTML.
  const inBrowser = useSyncExternalStore(noSubscription, () => true, () => false)
  const [shows, setShows] = useState<HomeShow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    loadHomeShows()
      .then(s => { if (!cancelled) setShows(s) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
    return () => { cancelled = true }
  }, [])

  // "Today" is evaluated in the browser, in Bay Area time, so past Shows drop off between builds.
  const listed = useMemo(() => {
    const filters = buildFilters(new URLSearchParams(filtersKey))
    if (shows) return { shows: filterShows(shows, filters) }
    if (!inBrowser) return { shows: page.firstShows, firstPage: true }  // as built
    if (filters) return { shows: null }                                  // the first page is unfiltered: wait
    const current = filterShows(page.firstShows, null)                    // drop dates that have passed
    return { shows: current, firstPage: true, count: page.listedCount - (page.firstShows.length - current.length) }
  }, [shows, filtersKey, inBrowser, page])

  if (error) {
    return (
      <p role="alert" className="flex items-center justify-center gap-1.5 text-danger py-12">
        <ExclamationTriangleIcon className="size-5 shrink-0" />
        Couldn&apos;t load the list of shows. Please try again later.
      </p>
    )
  }

  return (
    <ShowList
      shows={listed.shows}
      showCount={listed.firstPage ? (listed.count ?? page.listedCount) : undefined}
      dbTotal={page.totalUpcoming}
      filterOptions={page.filterOptions}
      firstPage={listed.firstPage}
    />
  )
}
