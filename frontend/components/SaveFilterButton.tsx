'use client'

import Link from 'next/link'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { BellIcon } from '@heroicons/react/16/solid'
import { describeFilters } from '@/lib/filters'
import { alertsPageUrl, supabase } from '@/lib/supabase'
import { useSession } from '@/lib/useSession'
import Toast from './Toast'

const INPUT = 'h-9 rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400'
const BUTTON = 'h-9 rounded bg-amber-500 px-3 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50'

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
        className="inline-flex items-center gap-1 rounded border border-amber-500 bg-white px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-transparent dark:text-amber-400 dark:hover:bg-amber-900/20"
        title={query ? 'Get a weekly email with the shows matching these filters' : 'Set a filter to get alerts for it'}
      >
        <BellIcon className="size-3.5 shrink-0" />
        Setup Alert
      </button>

      {open && query && (
        <form
          onSubmit={submit}
          className="absolute right-0 top-full z-20 mt-2 flex w-80 flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Get an email each week with the upcoming shows matching these filters.
          </p>
          <div className="flex flex-col gap-1">
            <label htmlFor="save-filter-name" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
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
                <label htmlFor="save-filter-email" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
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
            <p role="alert" className="text-xs text-red-600 dark:text-red-400">
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
