'use client'

import { useEffect, useMemo, useState } from 'react'
import { ArrowPathIcon, ExclamationTriangleIcon } from '@heroicons/react/20/solid'
import ShowList from './ShowList'
import { loadSiteData } from '@/lib/data'
import { filterShows } from '@/lib/filterShows'
import { buildFilters } from '@/lib/filters'
import { useQuery } from '@/lib/navigation'
import type { SiteData } from '@/lib/types'

/** Home page body: loads the exported data in the browser and lists the Shows matching the URL filters. */
export default function HomeShows() {
  const filtersKey = useQuery().toString()
  const [data, setData] = useState<SiteData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    loadSiteData()
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
    return () => { cancelled = true }
  }, [])

  // "Today" is evaluated in the browser, in Bay Area time, so past Shows drop off between exports.
  const shows = useMemo(
    () => (data ? filterShows(data.shows, buildFilters(new URLSearchParams(filtersKey))) : []),
    [data, filtersKey],
  )

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-ink-muted -mt-5">
        {data?.meta.emailSubject ?? 'Upcoming Bay Area music'} — curated by{' '}
        <a href="mailto:skoepke@stevelist.com" className="underline hover:text-ink-soft">
          Steve List
        </a>.
      </p>
      {error ? (
        <p role="alert" className="flex items-center justify-center gap-1.5 text-danger py-12">
          <ExclamationTriangleIcon className="size-5 shrink-0" />
          Couldn&apos;t load the list of shows. Please try again later.
        </p>
      ) : !data ? (
        <p className="flex items-center justify-center gap-1.5 text-ink-faint py-12">
          <ArrowPathIcon className="size-4 shrink-0 animate-spin" />
          Loading…
        </p>
      ) : (
        <ShowList shows={shows} dbTotal={data.meta.totalUpcoming} filterOptions={data.meta.filterOptions} />
      )}
    </div>
  )
}
