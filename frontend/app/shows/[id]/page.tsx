import { notFound } from 'next/navigation'
import { siteData } from '@/lib/siteData.server'
import ShowDetail from '@/components/ShowDetail'
import BackLink from '@/components/BackLink'

// One static page per exported Show; anything else is a 404.
export const dynamicParams = false

export function generateStaticParams() {
  return siteData().showIds().map(id => ({ id }))
}

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function ShowPage({ params }: PageProps) {
  const { id } = await params
  const show = siteData().show(Number(id))
  if (!show) notFound()

  return (
    <div className="flex flex-col gap-6">
      <BackLink />
      <ShowDetail show={show} />
    </div>
  )
}
