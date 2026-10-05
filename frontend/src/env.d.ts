/// <reference types="astro/client" />

interface ImportMetaEnv {
  /** Sign-in and Saved Filters (ADR 0003). Public by design; without them the Alerts features are hidden. */
  readonly PUBLIC_SUPABASE_URL?: string
  readonly PUBLIC_SUPABASE_ANON_KEY?: string
}
