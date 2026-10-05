import { BellIcon } from '@heroicons/react/16/solid'
import { href } from '@/lib/basePath'

/** The header's link to the Alerts page. The layout shows it only on builds with the Supabase settings. */
export default function AlertsLink() {
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
