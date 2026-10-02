import type { Metadata } from 'next'
import UnsubscribePage from '@/components/UnsubscribePage'

export const metadata: Metadata = {
  title: 'Unsubscribe — The List',
  description: 'Stop the weekly Alert email.',
  robots: { index: false },
}

export default function Page() {
  return <UnsubscribePage />
}
