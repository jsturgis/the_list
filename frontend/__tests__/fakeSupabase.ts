import { vi } from 'vitest'
import type { SavedFilter } from '@/lib/supabase'

/**
 * A stand-in for the Supabase browser client: just the calls the Alerts features make. Tests set who's
 * signed in, which Saved Filters exist and whether weekly Alerts are on, then check what was sent.
 */
export function fakeSupabase() {
  const state = {
    email: null as string | null,
    savedFilters: [] as SavedFilter[],
    // The Alert subscription row: created with the first Saved Filter (a database trigger does it for real).
    subscription: null as { enabled: boolean } | null,
    insertError: null as { message: string } | null,
  }
  const session = () => (state.email ? { user: { id: 'user-1', email: state.email } } : null)
  const listeners: ((event: string, s: ReturnType<typeof session>) => void)[] = []

  const savedFilters = {
    insert: vi.fn(async (row: { name: string; query: string }) => {
      if (state.insertError) return { error: state.insertError }
      state.savedFilters.push({ id: `id-${state.savedFilters.length + 1}`, created_at: '2026-10-02T00:00:00Z', ...row })
      state.subscription ??= { enabled: true }
      return { error: null }
    }),
    select: (_columns?: string, options?: { count?: string; head?: boolean }) =>
      options?.head
        ? Promise.resolve({ count: state.savedFilters.length, error: null })
        : { order: async () => ({ data: [...state.savedFilters], error: null }) },
    delete: () => ({
      eq: vi.fn(async (_column: string, id: string) => {
        state.savedFilters = state.savedFilters.filter(f => f.id !== id)
        return { error: null }
      }),
    }),
  }
  const subscriptions = {
    select: () => ({ maybeSingle: async () => ({ data: state.subscription ? { ...state.subscription } : null, error: null }) }),
    update: (values: { enabled: boolean }) => ({
      eq: vi.fn(async () => {
        if (state.subscription) state.subscription.enabled = values.enabled
        return { error: null }
      }),
    }),
  }

  const client = {
    auth: {
      getSession: vi.fn(async () => ({ data: { session: session() }, error: null })),
      onAuthStateChange: vi.fn((listener: (event: string, s: ReturnType<typeof session>) => void) => {
        listeners.push(listener)
        return { data: { subscription: { unsubscribe: vi.fn() } } }
      }),
      signInWithOtp: vi.fn<(args: { email: string; options?: { emailRedirectTo?: string } }) => Promise<{ error: null }>>(
        async () => ({ error: null }),
      ),
      signOut: vi.fn(async () => {
        state.email = null
        listeners.forEach(l => l('SIGNED_OUT', null))
        return { error: null }
      }),
    },
    insert: savedFilters.insert,
    from: vi.fn((table: string) => {
      if (table === 'saved_filters') return savedFilters
      if (table === 'alert_subscriptions') return subscriptions
      throw new Error(`unexpected table ${table}`)
    }),
  }
  return { client, state }
}
