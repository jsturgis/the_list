import { notFound } from 'next/navigation'
import { siteData } from '@/lib/siteData.server'
import BandDetail from '@/components/BandDetail'
import BackLink from '@/components/BackLink'

// One static page per exported Band; anything else is a 404.
export const dynamicParams = false

export function generateStaticParams() {
  return siteData().bandIds().map(id => ({ id }))
}

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function BandPage({ params }: PageProps) {
  const { id } = await params
  const data = siteData()
  const band = data.band(Number(id))
  if (!band) notFound()

  return (
    <div className="flex flex-col gap-6">
      <BackLink />
      <BandDetail band={band} upcomingShows={data.bandShows(band.id)} similarBands={data.similarBands(band.id)} />
    </div>
  )
}
