import { createClient, type SupabaseClient } from '@supabase/supabase-js'

/**
 * The browser's Supabase client, for sign-in and Saved Filters (ADR 0003). The URL and publishable key are
 * public by design: row-level security decides what each person can read and change. Null when the build
 * didn't get them (local builds, tests), and the Alerts features stay hidden.
 */
const url = process.env.NEXT_PUBLIC_SUPABASE_URL
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

// The implicit flow puts the session in the sign-in link itself, so the link works when opened on another
// device or browser (PKCE needs the browser that asked for it).
export const supabase: SupabaseClient | null =
  url && key && typeof window !== 'undefined' ? createClient(url, key, { auth: { flowType: 'implicit' } }) : null

/** The most Saved Filters (alerts) one person can have; the database enforces it (see the saved_filters trigger). */
export const MAX_ALERTS = 20

export interface SavedFilter {
  id: string
  name: string
  query: string
  created_at: string
}

/** Where a sign-in link returns to: the Alerts page, plus any filter waiting to be saved. */
export function alertsPageUrl(pending?: { name: string; query: string }): string {
  const url = new URL(`${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}/alerts/`, window.location.origin)
  if (pending) {
    url.searchParams.set('save', pending.query)
    url.searchParams.set('name', pending.name)
  }
  return url.toString()
}
