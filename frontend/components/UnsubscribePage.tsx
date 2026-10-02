'use client'

import Link from 'next/link'
import { useEffect, useState, useSyncExternalStore } from 'react'
import { supabase } from '@/lib/supabase'

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

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-4">
      {(state === 'loading' || state === 'working') && <p className="text-sm text-ink-muted">Unsubscribing…</p>}
      {state === 'unavailable' && (
        <p className="text-sm text-ink-muted">Alerts aren&apos;t available on this copy of the site.</p>
      )}
      {state === 'done' && (
        <>
          <h1 className="text-3xl font-bold text-ink">You&apos;re unsubscribed</h1>
          <p className="text-ink-soft">
            You won&apos;t get the weekly Alert email any more. Your alerts are kept, so you can turn the email back on
            any time from the{' '}
            <Link href="/alerts/" className="text-link underline">
              Alerts page
            </Link>
            .
          </p>
        </>
      )}
      {state === 'invalid' && (
        <>
          <h1 className="text-3xl font-bold text-ink">This unsubscribe link isn&apos;t valid</h1>
          <p className="text-ink-soft">
            It may be incomplete or from an old email. You can turn the weekly email off yourself on the{' '}
            <Link href="/alerts/" className="text-link underline">
              Alerts page
            </Link>{' '}
            after signing in.
          </p>
        </>
      )}
    </article>
  )
}
