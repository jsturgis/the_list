import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { BellIcon as BellOutline } from '@heroicons/react/24/outline'
import { BellAlertIcon as BellSolid } from '@heroicons/react/24/solid'
import { href } from '@/lib/basePath'
import { findSameFilter } from '@/lib/filters'
import { MAX_ALERTS, alertsAvailable, alertsPageUrl, supabase, type SavedFilter } from '@/lib/supabase'
import { usePopover } from '@/lib/usePopover'
import { useSession } from '@/lib/useSession'
import Toast from './Toast'

interface AlertBellProps {
  /** What the alert is for: a Band's Shows, or the Shows at a Venue. */
  kind: 'band' | 'venue'
  id: number
  name: string
}

/** The signed-in person's alerts. */
async function loadAlerts(): Promise<{ list: SavedFilter[] | null; error: string | null }> {
  if (!supabase) return { list: null, error: null }
  const { data, error } = await supabase.from('saved_filters').select('id, name, query, created_at').order('created_at')
  return error ? { list: null, error: error.message } : { list: data as SavedFilter[], error: null }
}

const INPUT = 'h-9 rounded-full border border-line-strong bg-field text-sm px-3 text-ink placeholder:text-ink-faint'
const BUTTON = 'h-9 rounded-full bg-accent px-4 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:opacity-50'

/**
 * A Band or Venue page's bell: a Saved Filter for that one Band or Venue (`bandId=3`, `venueId=2`), so its
 * Upcoming Shows come in the weekly Alert. Signed in, it saves or deletes that alert in one press; a visitor who
 * isn't signed in gets a sign-in link by email, and the Alerts page saves the alert once they follow it.
 */
export default function AlertBell({ kind, id, name }: AlertBellProps) {
  const session = useSession()
  const query = `${kind === 'band' ? 'bandId' : 'venueId'}=${id}`
  const shows = kind === 'band' ? `${name}'s upcoming shows` : `the upcoming shows at ${name}`
  // A signed-in visitor's alerts, to know whether this one is among them and whether there's room for it.
  const [saved, setSaved] = useState<SavedFilter[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const container = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => setOpen(false), [])
  const dismissToast = useCallback(() => setToast(null), [])
  usePopover(open, close, container, button)

  const signedIn = session.status === 'signedIn'
  useEffect(() => {
    if (!signedIn) return
    let cancelled = false
    loadAlerts().then(({ list, error }) => {
      if (cancelled) return
      if (error) setToast(error)
      else setSaved(list)
    })
    return () => { cancelled = true }
  }, [signedIn])

  // Decided at build time too, so a build without the Supabase settings never renders the bell and then drops it.
  if (!alertsAvailable() || session.status === 'unavailable') return null

  const alert = saved ? findSameFilter(saved, query) : undefined
  const on = signedIn && !!alert

  const press = async () => {
    if (!signedIn) {
      setOpen(!open)
      setError(null)
      return
    }
    if (!supabase || !saved) return
    setBusy(true)
    if (alert) {
      const { error } = await supabase.from('saved_filters').delete().eq('id', alert.id)
      if (error) setToast(error.message)
      else {
        setSaved(saved.filter(f => f.id !== alert.id))
        setToast(`Stopped alerts for ${name}`)
      }
    } else if (saved.length >= MAX_ALERTS) {
      setToast(`You have ${MAX_ALERTS} alerts, the most allowed. Delete one on the Alerts page to add ${name}.`)
    } else {
      const { error } = await supabase.from('saved_filters').insert({ name, query })
      if (error) setToast(error.message)
      else {
        setToast(`You'll get ${shows} in your weekly email`)
        const { list, error } = await loadAlerts()
        if (error) setToast(error)
        else setSaved(list)
      }
    }
    setBusy(false)
  }

  const sendLink = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) return
    setBusy(true)
    setError(null)
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: alertsPageUrl({ name, query }) },
    })
    setBusy(false)
    if (error) return setError(error.message)
    setOpen(false)
    setEmail('')
    setToast('Check your email for a sign-in link')
    button.current?.focus()
  }

  const Bell = on ? BellSolid : BellOutline
  return (
    // On phones the panel spans the page header's title row (this wrapper isn't positioned), wherever the bell
    // landed on it; from `sm` it hangs off the bell.
    <div ref={container} className="sm:relative">
      <button
        ref={button}
        type="button"
        onClick={press}
        disabled={session.status === 'loading' || (signedIn && (!saved || busy))}
        aria-pressed={signedIn ? on : undefined}
        aria-expanded={signedIn ? undefined : open}
        aria-label={`Get alerts for ${name}`}
        title={on ? `You get alerts for ${name}. Press to stop them.` : `Get a weekly email with ${shows}`}
        className={`rounded-full border p-2 disabled:opacity-50 ${on
          ? 'border-accent bg-accent-chip text-link'
          : 'border-line-strong bg-surface text-ink-soft hover:border-accent hover:text-link'}`}
      >
        <Bell className="size-6" aria-hidden="true" />
      </button>

      {open && (
        <form
          onSubmit={sendLink}
          className="absolute inset-x-0 top-full z-20 mt-2 flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-lg sm:left-auto sm:right-0 sm:w-80"
        >
          <p className="text-sm text-ink-soft">Get an email each week with {shows}.</p>
          <input
            type="email"
            required
            autoFocus
            autoComplete="email"
            aria-label="Email"
            placeholder="Email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            className={INPUT}
          />
          <button type="submit" disabled={busy} className={BUTTON}>
            Email me a sign-in link
          </button>
          {error && <p role="alert" className="text-xs text-danger">{error}</p>}
          <p className="text-xs text-ink-muted">
            Already have alerts? <a href={href('/alerts/')} className="text-link underline underline-offset-2">Sign in on the Alerts page</a>.
          </p>
        </form>
      )}
      {toast && <Toast onDismiss={dismissToast}>{toast}</Toast>}
    </div>
  )
}
