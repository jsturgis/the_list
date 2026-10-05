import { BellIcon } from '@heroicons/react/16/solid'
import { href } from '@/lib/basePath'
import { useSession } from '@/lib/useSession'

/** The header's link to the Alerts page; hidden on builds without Supabase settings. */
export default function AlertsLink() {
  const session = useSession()
  if (session.status === 'unavailable' || session.status === 'loading') return null
  return (
    <a
      href={href('/alerts/')}
      className="ml-auto inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink-soft hover:underline"
    >
      <BellIcon className="size-4 shrink-0" aria-hidden="true" />
      Your alerts
    </a>
  )
}
