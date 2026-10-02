'use client'

import Link from 'next/link'
import { useEffect, useState, type FormEvent } from 'react'
import { alertsPageUrl, supabase, type SavedFilter } from '@/lib/supabase'
import { useSession } from '@/lib/useSession'

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
        <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-50">Your alerts</h1>
        <p className="mt-1 text-zinc-600 dark:text-zinc-300">
          Each week, after the new edition is published, you get one email listing the upcoming shows that match your
          saved searches.
        </p>
      </header>

      {session.status === 'loading' && <p className="text-sm text-zinc-500">Loading…</p>}
      {session.status === 'unavailable' && (
        <p className="text-sm text-zinc-500">Alerts aren&apos;t available on this copy of the site.</p>
      )}
      {session.status === 'signedOut' && <SignInByEmail />}
      {session.status === 'signedIn' && (
        <section className="flex flex-col gap-3">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Signed in as {session.email}</p>
          {error && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}
          {savedFilters === null ? (
            <p className="text-sm text-zinc-500">Loading your saved searches…</p>
          ) : savedFilters.length === 0 ? (
            <p className="text-sm text-zinc-600 dark:text-zinc-300">
              No saved searches yet. Set some filters on the{' '}
              <Link href="/" className="text-amber-600 underline dark:text-amber-400">
                Shows list
              </Link>{' '}
              and choose Save search.
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
              {savedFilters.map(f => (
                <li key={f.id} className="py-2">
                  <Link href={`/?${f.query}`} className="font-medium text-zinc-900 hover:underline dark:text-zinc-50">
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
    if (error) setError(error.message)
    else setSent(true)
  }

  if (sent) return <p className="text-sm text-zinc-700 dark:text-zinc-300">Check your email for a sign-in link.</p>

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 max-w-sm">
      <p className="text-sm text-zinc-600 dark:text-zinc-300">Sign in to see and manage your saved searches.</p>
      <div className="flex flex-col gap-1">
        <label htmlFor="alerts-email" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
          Email
        </label>
        <input
          id="alerts-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          className="h-9 rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 text-zinc-900 dark:text-zinc-100"
        />
      </div>
      <button
        type="submit"
        disabled={sending}
        className="h-9 rounded bg-amber-500 px-3 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
      >
        Email me a sign-in link
      </button>
      {error && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </form>
  )
}
