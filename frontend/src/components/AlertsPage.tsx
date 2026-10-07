import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { TrashIcon } from '@heroicons/react/16/solid'
import { FIELD } from '@/lib/field'
import { href } from '@/lib/basePath'
import { MAX_ALERTS, alertsPageUrl, supabase, type SavedFilter } from '@/lib/supabase'
import { findSameFilter } from '@/lib/filters'
import { useSession } from '@/lib/useSession'
import { GhostLine, GhostRows, LoadingLabel } from './Ghost'
import PageHeader from './PageHeader'
import Section from './Section'
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
    <article className="flex flex-col gap-6">
      <PageHeader
        title="Your alerts"
        subtitle="You'll receive an email once a week if your saved search filter matches any upcoming shows."
      />

      {session.status === 'loading' && (
        // Not yet known whether this is the sign-in form or someone's alerts: a section's outline.
        <div data-ghost="" className="flex flex-col gap-3">
          <LoadingLabel>Loading…</LoadingLabel>
          <GhostLine className="h-7 w-32" />
          <div className="flex flex-col gap-3 rounded-lg bg-surface p-5">
            <GhostLine className="w-3/4" />
            <GhostLine className="h-9 w-full" />
            <GhostLine className="h-9 w-full" />
          </div>
        </div>
      )}
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
    const load = () =>
      Promise.all([
        client.from('saved_filters').select('id, name, query, created_at').order('created_at'),
        client.from('alert_subscriptions').select('enabled').maybeSingle(),
      ])
    ;(async () => {
      const pending = takePendingFilter()
      let [filters, subscription] = await load()
      // Save the filter the sign-in link carried, unless the person already has an alert for it.
      if (pending && !filters.error) {
        const same = findSameFilter((filters.data ?? []) as SavedFilter[], pending.query)
        if (same) {
          if (!cancelled) setToast(`You already have an alert for these filters: “${same.name}”`)
        } else {
          const { error } = await client.from('saved_filters').insert(pending)
          if (error && !cancelled) setError(error.message)
          ;[filters, subscription] = await load()
        }
      }
      if (cancelled) return
      if (filters.error) setError(filters.error.message)
      else setSavedFilters(filters.data as SavedFilter[])
      setWeekly(subscription.data ? subscription.data.enabled : null)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // After a delete, keyboard focus moves to a neighbouring alert (or the empty message), not the top of the page.
  const list = useRef<HTMLDivElement>(null)
  const [focusAfterDelete, setFocusAfterDelete] = useState<number | null>(null)
  useEffect(() => {
    if (focusAfterDelete === null || !list.current) return
    const links = list.current.querySelectorAll<HTMLElement>('[data-alert-link]')
    const target = links[Math.min(focusAfterDelete, links.length - 1)] ?? list.current.querySelector<HTMLElement>('[data-no-alerts]')
    target?.focus()
    setFocusAfterDelete(null)
  }, [focusAfterDelete, savedFilters])

  const remove = async (filter: SavedFilter) => {
    if (!supabase) return
    const { error } = await supabase.from('saved_filters').delete().eq('id', filter.id)
    if (error) {
      setError(error.message)
      return
    }
    setFocusAfterDelete(savedFilters?.findIndex(f => f.id === filter.id) ?? 0)
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
    <div className="flex flex-col gap-6">
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

      {savedFilters === null && !error && (
        <Section title="Weekly email">
          <div data-ghost="" className="flex items-center gap-2">
            <LoadingLabel>Loading your weekly email setting…</LoadingLabel>
            <GhostLine className="size-4 rounded" />
            <GhostLine className="w-56" />
          </div>
        </Section>
      )}
      {weekly !== null && (
        <Section title="Weekly email">
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
        </Section>
      )}

      <Section
        title="Your alerts"
        headingId="your-alerts-list"
        aside={savedFilters?.length ? `${savedFilters.length} of ${MAX_ALERTS} alerts` : undefined}
      >
      <div ref={list}>
      {savedFilters === null ? (
        <GhostRows label="Loading your alerts…" />
      ) : savedFilters.length === 0 ? (
        <p data-no-alerts="" tabIndex={-1} className="text-sm text-ink-soft outline-none">
          No alerts yet. Set some filters on the{' '}
          <a href={href('/')} className="text-link underline underline-offset-2">
            Shows list
          </a>{' '}
          and choose Save search.
        </p>
      ) : (
        <div>
          <ul className="flex flex-col divide-y divide-line-subtle">
            {savedFilters.map(f => (
              <li key={f.id} className="flex items-center justify-between gap-4 py-2">
                <a href={href(`/?${f.query}`)} data-alert-link="" className="min-w-0 truncate font-medium text-ink hover:underline">
                  {f.name}
                </a>
                <button
                  type="button"
                  onClick={() => remove(f)}
                  aria-label={`Delete ${f.name}`}
                  title="Delete"
                  className="shrink-0 rounded-full p-1 text-ink-faint hover:bg-muted hover:text-danger"
                >
                  <TrashIcon className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      </div>
      </Section>

      {toast && <Toast onDismiss={dismissToast}>{toast}</Toast>}
    </div>
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
      <Section title="Sign in">
      <form onSubmit={submit} className="flex flex-col gap-3 max-w-sm">
        <p className="text-sm text-ink-soft">We&apos;ll email you a link to see and manage your alerts.</p>
        <input
          type="email"
          required
          autoComplete="email"
          aria-label="Email"
          placeholder="Email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          className={`${FIELD} px-3`}
        />
        <button
          type="submit"
          disabled={sending}
          className="h-9 rounded-full bg-accent px-4 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:opacity-50"
        >
          Email me a sign-in link
        </button>
        {error && (
          <p role="alert" className="text-xs text-danger">
            {error}
          </p>
        )}
      </form>
      </Section>
      {sent && <Toast onDismiss={dismissToast}>Check your email for a sign-in link.</Toast>}
    </>
  )
}
