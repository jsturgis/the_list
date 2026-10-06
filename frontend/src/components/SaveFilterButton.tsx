import { useCallback, useRef, useState, type FormEvent } from 'react'
import { BellIcon } from '@heroicons/react/16/solid'
import { href } from '@/lib/basePath'
import { describeFilters, findSameFilter } from '@/lib/filters'
import { MAX_ALERTS, alertsAvailable, alertsPageUrl, supabase } from '@/lib/supabase'
import { usePopover } from '@/lib/usePopover'
import { useSession } from '@/lib/useSession'
import Toast from './Toast'

const INPUT = 'h-9 rounded-full border border-line-strong bg-field text-sm px-3 text-ink placeholder:text-ink-faint'
const BUTTON = 'h-9 rounded-full bg-accent px-4 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:opacity-50'

type Done = 'linkSent' | 'saved'

/**
 * Saves the Shows list's current filters as a Saved Filter, for the weekly Alert. A visitor who isn't
 * signed in gets a sign-in link by email; the Alerts page saves the filter once they follow it.
 */
export default function SaveFilterButton({ query, pinnedName }: { query: string; pinnedName?: string }) {
  const session = useSession()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<Done | null>(null)
  // A signed-in visitor's alerts, read when the form opens: how many, and whether these filters are one.
  const [existing, setExisting] = useState<{ name: string; query: string }[] | null>(null)
  const container = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const dismissToast = useCallback(() => {
    // If the keyboard was on the toast, keep it nearby rather than losing it to the top of the page.
    if (container.current?.contains(document.activeElement)) button.current?.focus()
    setDone(null)
  }, [])

  const close = useCallback(() => setOpen(false), [])
  usePopover(open, close, container, button)

  // Decided at build time too, so a build without the Supabase settings never renders the button and then drops it.
  if (!alertsAvailable() || session.status === 'unavailable') return null

  const toggle = () => {
    if (!open) {
      setName(describeFilters(new URLSearchParams(query), pinnedName))
      setExisting(null)
      if (session.status === 'signedIn' && supabase) {
        supabase
          .from('saved_filters')
          .select('name, query')
          .order('created_at')
          .then(({ data }) => setExisting(data ?? null))
      }
    }
    setOpen(!open)
    setError(null)
  }
  const used = existing?.length ?? null
  const atLimit = used !== null && used >= MAX_ALERTS
  const duplicate = existing ? findSameFilter(existing, query) : undefined

  const finish = (result: Done) => {
    setOpen(false)
    setName('')
    setDone(result)
    button.current?.focus()  // the form is gone: keep the keyboard where it was, not at the top of the page
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) return
    setSending(true)
    setError(null)
    const { error } =
      session.status === 'signedIn'
        ? await supabase.from('saved_filters').insert({ name: name.trim(), query })
        : await supabase.auth.signInWithOtp({
            email: email.trim(),
            options: { emailRedirectTo: alertsPageUrl({ name: name.trim(), query }) },
          })
    setSending(false)
    if (error) setError(error.message)
    else finish(session.status === 'signedIn' ? 'saved' : 'linkSent')
  }

  // On phones the panel spans the filter bar's last row (the wrapper isn't positioned); from `sm` it hangs off the button.
  return (
    <div ref={container} className="flex-1 sm:relative sm:flex-none">
      <button
        ref={button}
        type="button"
        onClick={toggle}
        disabled={!query || session.status === 'loading'}
        aria-expanded={open}
        className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-full bg-accent px-4 text-sm font-bold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        title={query ? 'Get a weekly email with the shows matching these filters' : 'Set a filter to save it as a search'}
      >
        <BellIcon className="size-4 shrink-0" />
        Save search
      </button>

      {open && query && (
        <form
          onSubmit={submit}
          className="absolute inset-x-0 top-full z-20 mt-2 flex flex-col sm:left-auto sm:right-0 sm:w-80 gap-3 rounded-lg border border-line bg-surface p-4 shadow-lg"
        >
          <p className="text-xs text-ink-muted">
            Get an email each week with the upcoming shows matching these filters.
          </p>
          <div className="flex flex-col gap-1">
            <label htmlFor="save-filter-name" className="text-xs font-medium text-ink-soft">
              Name
            </label>
            <input
              id="save-filter-name"
              required
              autoFocus
              maxLength={80}
              placeholder="e.g. East Bay punk"
              value={name}
              onChange={e => setName(e.target.value)}
              className={INPUT}
            />
          </div>
          {session.status === 'signedIn' ? (
            <>
              {duplicate ? (
                <p className="text-xs text-ink-soft">
                  You already have an alert for these filters: “{duplicate.name}”.{' '}
                  <a href={href('/alerts/')} className="text-link underline">
                    Manage your alerts
                  </a>
                </p>
              ) : atLimit ? (
                <p className="text-xs text-danger">
                  You have {MAX_ALERTS} alerts, the most allowed.{' '}
                  <a href={href('/alerts/')} className="underline">
                    Delete one
                  </a>{' '}
                  to set up another.
                </p>
              ) : (
                used !== null && (
                  <p className="text-xs text-ink-muted">
                    {used} of {MAX_ALERTS} alerts used
                  </p>
                )
              )}
              <button type="submit" disabled={sending || atLimit || !!duplicate} className={BUTTON}>
                Save
              </button>
            </>
          ) : (
            <>
              <div className="flex flex-col gap-1">
                <label htmlFor="save-filter-email" className="text-xs font-medium text-ink-soft">
                  Email
                </label>
                <input
                  id="save-filter-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className={INPUT}
                />
              </div>
              <button type="submit" disabled={sending} className={BUTTON}>
                Email me a sign-in link
              </button>
            </>
          )}
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}
        </form>
      )}

      {done && (
        <Toast onDismiss={dismissToast}>
          {done === 'linkSent' ? (
            'Check your email for a sign-in link. Opening it sets up this alert.'
          ) : (
            <>
              Alert set up. You&apos;ll get the matching shows by email each week.{' '}
              <a href={href('/alerts/')} className="font-medium underline">
                Manage your alerts
              </a>
            </>
          )}
        </Toast>
      )}
    </div>
  )
}
