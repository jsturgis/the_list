import { notFound } from 'next/navigation'
import { loadBand } from '@/lib/bands'
import BandDetail from '@/components/BandDetail'
import Modal from '@/components/Modal'

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function BandModal({ params }: PageProps) {
  const { id } = await params
  const data = await loadBand(id)

  if (!data) notFound()

  return (
    <Modal>
      <BandDetail band={data.band} upcomingShows={data.upcomingShows} />
    </Modal>
  )
}
