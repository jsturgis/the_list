import { notFound } from 'next/navigation'
import { gqlClient } from '@/lib/graphql'
import { VENUE_QUERY, VENUE_SHOWS_QUERY, ALL_VENUES_STATIC_QUERY } from '@/lib/queries'
import type { Venue, Show } from '@/lib/types'
import VenueDetail from '@/components/VenueDetail'
import BackToShows from '@/components/BackToShows'

export async function generateStaticParams() {
  try {
    const data = await gqlClient.request<{ shows: { venue: { id: number } }[] }>(
      ALL_VENUES_STATIC_QUERY,
    )
    const ids = new Set<number>()
    for (const show of data.shows) {
      ids.add(show.venue.id)
    }
    return Array.from(ids).map(id => ({ id: String(id) }))
  } catch {
    return []
  }
}

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function VenuePage({ params }: PageProps) {
  const { id } = await params
  let venue: Venue | null = null
  let upcomingShows: Show[] = []

  try {
    const venueData = await gqlClient.request<{ venue: Venue | null }>(VENUE_QUERY, { id })
    venue = venueData.venue
    if (venue) {
      const showsData = await gqlClient.request<{ shows: Show[] }>(VENUE_SHOWS_QUERY, {
        venueId: venue.id,
      })
      upcomingShows = showsData.shows
    }
  } catch {
    // fall through to notFound
  }

  if (!venue) notFound()

  return (
    <div className="flex flex-col gap-6">
      <BackToShows />
      <VenueDetail venue={venue} upcomingShows={upcomingShows} />
    </div>
  )
}
