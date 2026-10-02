'use client'

import Link from 'next/link'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { BellIcon } from '@heroicons/react/16/solid'
import { describeFilters } from '@/lib/filters'
import { alertsPageUrl, supabase } from '@/lib/supabase'
import { useSession } from '@/lib/useSession'
import Toast from './Toast'

const INPUT = 'h-9 rounded border border-line-strong bg-field text-sm px-2 text-ink placeholder:text-ink-faint'
const BUTTON = 'h-9 rounded bg-accent px-3 text-sm font-medium text-on-accent hover:bg-accent-hover disabled:opacity-50'

type Done = 'linkSent' | 'saved'

/**
 * Saves the Shows list's current filters as a Saved Filter, for the weekly Alert. A visitor who isn't
 * signed in gets a sign-in link by email; the Alerts page saves the filter once they follow it.
 */
export default function SaveFilterButton({ query }: { query: string }) {
  const session = useSession()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<Done | null>(null)
  const container = useRef<HTMLDivElement>(null)
  const dismissToast = useCallback(() => setDone(null), [])

  // The form closes with Escape or a click anywhere outside it.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    const onPointer = (e: MouseEvent) => {
      if (container.current && !container.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
    }
  }, [open])

  if (session.status === 'unavailable') return null

  const toggle = () => {
    if (!open) setName(describeFilters(new URLSearchParams(query)))
    setOpen(!open)
    setError(null)
  }

  const finish = (result: Done) => {
    setOpen(false)
    setName('')
    setDone(result)
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

  return (
    <div ref={container} className="relative">
      <button
        type="button"
        onClick={toggle}
        disabled={!query || session.status === 'loading'}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded border border-accent bg-surface px-2.5 py-1 text-xs font-medium text-link hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
        title={query ? 'Get a weekly email with the shows matching these filters' : 'Set a filter to get alerts for it'}
      >
        <BellIcon className="size-3.5 shrink-0" />
        Setup Alert
      </button>

      {open && query && (
        <form
          onSubmit={submit}
          className="absolute right-0 top-full z-20 mt-2 flex w-80 flex-col gap-3 rounded-lg border border-line bg-surface p-4 shadow-lg"
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
            <button type="submit" disabled={sending} className={BUTTON}>
              Save
            </button>
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
              <Link href="/alerts/" className="font-medium underline">
                Manage your alerts
              </Link>
            </>
          )}
        </Toast>
      )}
    </div>
  )
}
