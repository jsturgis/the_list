'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { TrashIcon } from '@heroicons/react/16/solid'
import { MAX_ALERTS, alertsPageUrl, supabase, type SavedFilter } from '@/lib/supabase'
import { useSession } from '@/lib/useSession'
import Toast from './Toast'

/** The Saved Filter a sign-in link carries (?save=<query>&name=<name>), removed from the address bar. */
function takePendingFilter(): { name: string; query: string } | null {
  const params = new URLSearchParams(window.location.search)
  const query = params.get('save')
  const name = params.get('name')?.trim()
  if (!query) return null
  window.history.replaceState(window.history.state, '', window.location.pathname)
  return { name: name || 'Saved search', query }
}

export default function AlertsPage() {
  const session = useSession()

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      <header>
        <h1 className="text-3xl font-bold text-ink">Your alerts</h1>
        <p className="mt-1 text-ink-soft">
          You&apos;ll receive an email once a week if your saved search filter matches any upcoming shows.
        </p>
      </header>

      {session.status === 'loading' && <p className="text-sm text-ink-muted">Loading…</p>}
      {session.status === 'unavailable' && (
        <p className="text-sm text-ink-muted">Alerts aren&apos;t available on this copy of the site.</p>
      )}
      {session.status === 'signedOut' && <SignInByEmail />}
      {session.status === 'signedIn' && <YourAlerts email={session.email} userId={session.userId} />}
    </article>
  )
}

/** A signed-in person's alerts: the list (open, delete), the weekly email switch, and sign out. */
function YourAlerts({ email, userId }: { email: string; userId: string }) {
  const [savedFilters, setSavedFilters] = useState<SavedFilter[] | null>(null)
  // Whether weekly emails are on; null until loaded, or when there's no subscription yet (no alerts saved).
  const [weekly, setWeekly] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const dismissToast = useCallback(() => setToast(null), [])

  useEffect(() => {
    const client = supabase
    if (!client) return
    let cancelled = false
    ;(async () => {
      const pending = takePendingFilter()
      if (pending) {
        const { error } = await client.from('saved_filters').insert(pending)
        if (error && !cancelled) setError(error.message)
      }
      const [filters, subscription] = await Promise.all([
        client.from('saved_filters').select('id, name, query, created_at').order('created_at'),
        client.from('alert_subscriptions').select('enabled').maybeSingle(),
      ])
      if (cancelled) return
      if (filters.error) setError(filters.error.message)
      else setSavedFilters(filters.data as SavedFilter[])
      setWeekly(subscription.data ? subscription.data.enabled : null)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const remove = async (filter: SavedFilter) => {
    if (!supabase) return
    const { error } = await supabase.from('saved_filters').delete().eq('id', filter.id)
    if (error) {
      setError(error.message)
      return
    }
    setSavedFilters(fs => fs?.filter(f => f.id !== filter.id) ?? null)
    setToast(`Deleted “${filter.name}”`)
  }

  const setWeeklyEmails = async (enabled: boolean) => {
    if (!supabase) return
    setWeekly(enabled)
    const { error } = await supabase.from('alert_subscriptions').update({ enabled }).eq('user_id', userId)
    if (error) {
      setWeekly(!enabled)
      setError(error.message)
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4 text-sm text-ink-muted">
        <span>Signed in as {email}</span>
        <button type="button" onClick={() => supabase?.auth.signOut()} className="underline hover:text-ink-soft">
          Sign out
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {weekly !== null && (
        <div className="flex flex-col gap-1 rounded-lg border border-line bg-panel p-3">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={weekly}
              onChange={e => setWeeklyEmails(e.target.checked)}
              className="rounded border-line-strong accent-accent"
            />
            Email me these alerts each week
          </label>
          {!weekly && (
            <p className="text-xs text-ink-muted">Weekly emails are off. Your alerts are kept, ready to turn back on.</p>
          )}
        </div>
      )}

      {savedFilters === null ? (
        <p className="text-sm text-ink-muted">Loading your alerts…</p>
      ) : savedFilters.length === 0 ? (
        <p className="text-sm text-ink-soft">
          No alerts yet. Set some filters on the{' '}
          <Link href="/" className="text-link underline">
            Shows list
          </Link>{' '}
          and choose Setup Alert.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-ink-muted">
            {savedFilters.length} of {MAX_ALERTS} alerts
          </p>
          <ul className="flex flex-col divide-y divide-line-subtle">
            {savedFilters.map(f => (
              <li key={f.id} className="flex items-center justify-between gap-4 py-2">
                <Link href={`/?${f.query}`} className="min-w-0 truncate font-medium text-ink hover:underline">
                  {f.name}
                </Link>
                <button
                  type="button"
                  onClick={() => remove(f)}
                  aria-label={`Delete ${f.name}`}
                  title="Delete"
                  className="shrink-0 rounded p-1 text-ink-faint hover:bg-muted hover:text-danger"
                >
                  <TrashIcon className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {toast && <Toast onDismiss={dismissToast}>{toast}</Toast>}
    </section>
  )
}

function SignInByEmail() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)
  const dismissToast = useCallback(() => setSent(false), [])
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) return
    setSending(true)
    setError(null)
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: alertsPageUrl() },
    })
    setSending(false)
    if (error) {
      setError(error.message)
    } else {
      setEmail('')
      setSent(true)
    }
  }

  return (
    <>
      <form onSubmit={submit} className="flex flex-col gap-3 max-w-sm">
        <p className="text-sm text-ink-soft">Sign in to see and manage your alerts.</p>
        <div className="flex flex-col gap-1">
          <label htmlFor="alerts-email" className="text-xs font-medium text-ink-soft">
            Email
          </label>
          <input
            id="alerts-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="h-9 rounded border border-line-strong bg-field text-sm px-2 text-ink"
          />
        </div>
        <button
          type="submit"
          disabled={sending}
          className="h-9 rounded bg-accent px-3 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:opacity-50"
        >
          Email me a sign-in link
        </button>
        {error && (
          <p role="alert" className="text-xs text-danger">
            {error}
          </p>
        )}
      </form>
      {sent && <Toast onDismiss={dismissToast}>Check your email for a sign-in link.</Toast>}
    </>
  )
}
