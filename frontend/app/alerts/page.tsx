import type { Metadata } from 'next'
import AlertsPage from '@/components/AlertsPage'

export const metadata: Metadata = {
  title: 'Your alerts — The List',
  description: 'Saved searches and the weekly email of matching SF Bay Area shows.',
}

export default function Page() {
  return <AlertsPage />
}
