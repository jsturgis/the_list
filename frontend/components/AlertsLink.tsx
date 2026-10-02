'use client'

import Link from 'next/link'
import { BellIcon } from '@heroicons/react/16/solid'
import { useSession } from '@/lib/useSession'

/** The header's link to the Alerts page; hidden on builds without Supabase settings. */
export default function AlertsLink() {
  const session = useSession()
  if (session.status === 'unavailable' || session.status === 'loading') return null
  return (
    <Link
      href="/alerts/"
      className="ml-auto inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-700 hover:underline dark:text-zinc-400 dark:hover:text-zinc-200"
    >
      <BellIcon className="size-4 shrink-0" aria-hidden="true" />
      Your alerts
    </Link>
  )
}
