import { vi } from 'vitest'
import type { SavedFilter } from '@/lib/supabase'

/**
 * A stand-in for the Supabase browser client: just the calls the Alerts features make. Tests set who's
 * signed in and which Saved Filters exist, then check what was sent.
 */
export function fakeSupabase() {
  const state = {
    email: null as string | null,
    savedFilters: [] as SavedFilter[],
    insertError: null as { message: string } | null,
  }
  const session = () => (state.email ? { user: { email: state.email } } : null)

  const client = {
    auth: {
      getSession: vi.fn(async () => ({ data: { session: session() }, error: null })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      signInWithOtp: vi.fn<(args: { email: string; options?: { emailRedirectTo?: string } }) => Promise<{ error: null }>>(
        async () => ({ error: null }),
      ),
    },
    insert: vi.fn(async (row: { name: string; query: string }) => {
      if (state.insertError) return { error: state.insertError }
      state.savedFilters.push({ id: `id-${state.savedFilters.length + 1}`, created_at: '2026-10-02T00:00:00Z', ...row })
      return { error: null }
    }),
    from: vi.fn((table: string) => {
      if (table !== 'saved_filters') throw new Error(`unexpected table ${table}`)
      return {
        insert: client.insert,
        select: () => ({ order: async () => ({ data: [...state.savedFilters], error: null }) }),
      }
    }),
  }
  return { client, state }
}
