'use client'

import Link from 'next/link'
import { useState, type FormEvent } from 'react'
import { BookmarkIcon } from '@heroicons/react/16/solid'
import { alertsPageUrl, supabase } from '@/lib/supabase'
import { useSession } from '@/lib/useSession'

const INPUT = 'h-9 rounded border border-zinc-300 dark:border-zinc-600 bg-white dark:bg-zinc-800 text-sm px-2 text-zinc-900 dark:text-zinc-100 placeholder:text-zinc-400'
const BUTTON = 'h-9 rounded bg-amber-500 px-3 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50'

type Step = 'form' | 'sending' | 'linkSent' | 'saved'

/**
 * Saves the Shows list's current filters as a Saved Filter, for the weekly Alert. A visitor who isn't
 * signed in gets a sign-in link by email; the Alerts page saves the filter once they follow it.
 */
export default function SaveFilterButton({ query }: { query: string }) {
  const session = useSession()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [step, setStep] = useState<Step>('form')
  const [error, setError] = useState<string | null>(null)

  if (session.status === 'unavailable') return null

  const toggle = () => {
    setOpen(o => !o)
    setStep('form')
    setError(null)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!supabase) return
    setStep('sending')
    setError(null)
    if (session.status === 'signedIn') {
      const { error } = await supabase.from('saved_filters').insert({ name: name.trim(), query })
      if (error) {
        setError(error.message)
        setStep('form')
      } else {
        setStep('saved')
      }
    } else {
      const { error } = await supabase.auth.signInWithOtp({
        email: email.trim(),
        options: { emailRedirectTo: alertsPageUrl({ name: name.trim(), query }) },
      })
      if (error) {
        setError(error.message)
        setStep('form')
      } else {
        setStep('linkSent')
      }
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={toggle}
        disabled={!query || session.status === 'loading'}
        aria-expanded={open}
        className="inline-flex items-center gap-0.5 text-xs text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 underline disabled:no-underline disabled:opacity-50"
        title={query ? 'Get a weekly email with the shows matching these filters' : 'Set a filter to save it'}
      >
        <BookmarkIcon className="size-3.5 shrink-0" />
        Save search
      </button>

      {open && query && (
        <div className="absolute right-0 top-full z-20 mt-2 w-80 rounded-lg border border-zinc-200 bg-white p-4 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          {step === 'linkSent' ? (
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              Check your email for a sign-in link. Opening it saves this search.
            </p>
          ) : step === 'saved' ? (
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              Saved. You&apos;ll get the matching shows by email each week.{' '}
              <Link href="/alerts/" className="text-amber-600 underline dark:text-amber-400">
                Manage your alerts
              </Link>
            </p>
          ) : (
            <form onSubmit={submit} className="flex flex-col gap-3">
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
                  maxLength={80}
                  placeholder="e.g. East Bay punk"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  className={INPUT}
                />
              </div>
              {session.status === 'signedIn' ? (
                <button type="submit" disabled={step === 'sending'} className={BUTTON}>
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
                  <button type="submit" disabled={step === 'sending'} className={BUTTON}>
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
        </div>
      )}
    </div>
  )
}
