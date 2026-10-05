import { useEffect, useState, useSyncExternalStore } from 'react'
import { href } from '@/lib/basePath'
import { supabase } from '@/lib/supabase'
import PageHeader from './PageHeader'

const noSubscription = () => () => {}

/** The token in the link (?token=…): '' when there's none, null while prerendering and hydrating. */
function useToken(): string | null {
  return useSyncExternalStore(
    noSubscription,
    () => new URLSearchParams(window.location.search).get('token')?.trim() ?? '',
    () => null,
  )
}

/**
 * Where an Alert email's unsubscribe link lands. It turns that person's weekly Alerts off without signing in
 * (the database's unsubscribe function, by the link's token) and keeps their Saved Filters.
 */
export default function UnsubscribePage() {
  const token = useToken()
  const [result, setResult] = useState<'done' | 'invalid' | null>(null)

  useEffect(() => {
    if (!token || !supabase) return
    supabase
      .rpc('unsubscribe', { token })
      .then(({ data, error }) => setResult(!error && data === true ? 'done' : 'invalid'))
  }, [token])

  const state = token === null ? 'loading' : !supabase ? 'unavailable' : !token ? 'invalid' : (result ?? 'working')

  const alertsLink = <a href={href('/alerts/')} className="text-link underline underline-offset-2">Alerts page</a>

  return (
    <article className="flex flex-col gap-6">
      {(state === 'loading' || state === 'working') && <PageHeader title="Unsubscribe" subtitle="Unsubscribing…" />}
      {state === 'unavailable' && (
        <PageHeader title="Unsubscribe" subtitle="Alerts aren't available on this copy of the site." />
      )}
      {state === 'done' && (
        <PageHeader
          title="You're unsubscribed"
          subtitle={<>
            You won&apos;t get the weekly Alert email any more. Your alerts are kept, so you can turn the email back on
            any time from the {alertsLink}.
          </>}
        />
      )}
      {state === 'invalid' && (
        <PageHeader
          title="This unsubscribe link isn't valid"
          subtitle={<>It may be incomplete or from an old email. You can turn the weekly email off yourself on the {alertsLink} after signing in.</>}
        />
      )}
    </article>
  )
}
