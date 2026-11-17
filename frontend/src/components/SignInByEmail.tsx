import { useCallback, useState, type FormEvent } from 'react'
import { FIELD } from '@/lib/field'
import { supabase } from '@/lib/supabase'
import Section from './Section'
import Toast from './Toast'

/**
 * Sign in by email (Supabase's magic link), for the pages that need someone signed in: Alerts, Admin. The link
 * returns to `redirectTo()`.
 */
export default function SignInByEmail({ redirectTo, intro }: { redirectTo: () => string; intro: string }) {
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
      options: { emailRedirectTo: redirectTo() },
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
        <p className="text-sm text-ink-soft">{intro}</p>
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
