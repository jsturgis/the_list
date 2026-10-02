'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { alertsPageUrl, supabase, type SavedFilter } from '@/lib/supabase'
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
  const [savedFilters, setSavedFilters] = useState<SavedFilter[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const client = supabase
    if (session.status !== 'signedIn' || !client) return
    let cancelled = false
    ;(async () => {
      const pending = takePendingFilter()
      if (pending) {
        const { error } = await client.from('saved_filters').insert(pending)
        if (error && !cancelled) setError(error.message)
      }
      const { data, error } = await client.from('saved_filters').select('id, name, query, created_at').order('created_at')
      if (cancelled) return
      if (error) setError(error.message)
      else setSavedFilters(data as SavedFilter[])
    })()
    return () => {
      cancelled = true
    }
  }, [session.status])

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      <header>
        <h1 className="text-3xl font-bold text-ink">Your alerts</h1>
        <p className="mt-1 text-ink-soft">
          Each week, after the new edition is published, you get one email listing the upcoming shows that match your
          alerts.
        </p>
      </header>

      {session.status === 'loading' && <p className="text-sm text-ink-muted">Loading…</p>}
      {session.status === 'unavailable' && (
        <p className="text-sm text-ink-muted">Alerts aren&apos;t available on this copy of the site.</p>
      )}
      {session.status === 'signedOut' && <SignInByEmail />}
      {session.status === 'signedIn' && (
        <section className="flex flex-col gap-3">
          <p className="text-sm text-ink-muted">Signed in as {session.email}</p>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
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
            <ul className="flex flex-col divide-y divide-line-subtle">
              {savedFilters.map(f => (
                <li key={f.id} className="py-2">
                  <Link href={`/?${f.query}`} className="font-medium text-ink hover:underline">
                    {f.name}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </article>
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
