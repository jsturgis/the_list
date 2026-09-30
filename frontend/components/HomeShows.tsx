'use client'

import { useEffect, useState } from 'react'
import ShowList from './ShowList'
import { loadSiteData, upcomingShows } from '@/lib/data'
import type { Show, SiteData } from '@/lib/types'

/** Home page body: loads the exported data in the browser and lists Upcoming Shows. */
export default function HomeShows() {
  const [data, setData] = useState<SiteData | null>(null)
  const [shows, setShows] = useState<Show[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    loadSiteData()
      .then(d => {
        if (cancelled) return
        setData(d)
        setShows(upcomingShows(d.shows))  // "today" in Bay Area time, evaluated in the browser
      })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-zinc-500 dark:text-zinc-400 -mt-5">
        {data?.meta.emailSubject ?? 'Upcoming Bay Area music'} — curated by{' '}
        <a href="mailto:skoepke@stevelist.com" className="underline hover:text-zinc-700 dark:hover:text-zinc-300">
          Steve List
        </a>.
      </p>
      {error ? (
        <p role="alert" className="text-center text-red-600 dark:text-red-400 py-12">
          Couldn&apos;t load the list of shows. Please try again later.
        </p>
      ) : !data ? (
        <p className="text-center text-zinc-400 dark:text-zinc-500 py-12">Loading…</p>
      ) : (
        <ShowList shows={shows} dbTotal={data.meta.totalUpcoming} filterOptions={data.meta.filterOptions} />
      )}
    </div>
  )
}
