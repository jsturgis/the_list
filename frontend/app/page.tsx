import { Suspense } from 'react'
import { gqlClient } from '@/lib/graphql'
import { SHOWS_QUERY } from '@/lib/queries'
import type { Show } from '@/lib/types'
import ShowList from '@/components/ShowList'

async function fetchShows(): Promise<Show[]> {
  try {
    const data = await gqlClient.request<{ shows: Show[] }>(SHOWS_QUERY)
    return data.shows
  } catch {
    return []
  }
}

export default async function Home() {
  const shows = await fetchShows()

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">This Week&apos;s Shows</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
          Upcoming Bay Area music — curated by Steve List.
        </p>
      </div>
      <Suspense>
        <ShowList shows={shows} />
      </Suspense>
    </div>
  )
}
