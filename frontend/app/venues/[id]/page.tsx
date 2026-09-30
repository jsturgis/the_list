import { notFound } from 'next/navigation'
import { siteData } from '@/lib/siteData.server'
import VenueDetail from '@/components/VenueDetail'
import BackLink from '@/components/BackLink'

// One static page per exported Venue; anything else is a 404.
export const dynamicParams = false

export function generateStaticParams() {
  return siteData().venueIds().map(id => ({ id }))
}

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function VenuePage({ params }: PageProps) {
  const { id } = await params
  const data = siteData()
  const venue = data.venue(Number(id))
  if (!venue) notFound()

  return (
    <div className="flex flex-col gap-6">
      <BackLink />
      <VenueDetail venue={venue} upcomingShows={data.venueShows(venue.id)} />
    </div>
  )
}
