import { notFound } from 'next/navigation'
import { gqlClient } from '@/lib/graphql'
import { BAND_QUERY, BAND_SHOWS_QUERY, ALL_BANDS_STATIC_QUERY } from '@/lib/queries'
import type { Band, Show } from '@/lib/types'
import BandDetail from '@/components/BandDetail'
import Link from 'next/link'

export async function generateStaticParams() {
  try {
    const data = await gqlClient.request<{ shows: { acts: { band: { id: number } }[] }[] }>(
      ALL_BANDS_STATIC_QUERY,
    )
    const ids = new Set<number>()
    for (const show of data.shows) {
      for (const act of show.acts) {
        ids.add(act.band.id)
      }
    }
    return Array.from(ids).map(id => ({ id: String(id) }))
  } catch {
    return []
  }
}

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function BandPage({ params }: PageProps) {
  const { id } = await params
  let band: Band | null = null
  let upcomingShows: Show[] = []

  try {
    const bandData = await gqlClient.request<{ band: Band | null }>(BAND_QUERY, { id })
    band = bandData.band
    if (band) {
      const showsData = await gqlClient.request<{ shows: Show[] }>(BAND_SHOWS_QUERY, {
        bandId: band.id,
      })
      upcomingShows = showsData.shows
    }
  } catch {
    // fall through to notFound
  }

  if (!band) notFound()

  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/"
        className="text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
      >
        ← Back to all shows
      </Link>
      <BandDetail band={band} upcomingShows={upcomingShows} />
    </div>
  )
}
