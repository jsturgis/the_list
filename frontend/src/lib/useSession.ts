import { useEffect, useState, useSyncExternalStore } from 'react'
import { isAdmin } from './eventUrls'
import { supabase } from './supabase'

export type SessionState =
  | { status: 'loading' }
  | { status: 'unavailable' } // the build has no Supabase settings: the Alerts features stay hidden
  | { status: 'signedOut' }
  | { status: 'signedIn'; email: string; userId: string; isAdmin: boolean }

const noSubscription = () => () => {}

/**
 * Who's signed in, kept up to date as they sign in or out. 'loading' while prerendering and hydrating, so the
 * static page and the first browser render match.
 */
export function useSession(): SessionState {
  const inBrowser = useSyncExternalStore(noSubscription, () => true, () => false)
  const [signedIn, setSignedIn] = useState<SessionState | null>(null)

  useEffect(() => {
    const client = supabase
    if (!client) return
    let active = true
    const apply = (session: { user: { id: string; email?: string; app_metadata?: Record<string, unknown> } } | null) => {
      if (active) {
        setSignedIn(
          session
            ? {
                status: 'signedIn',
                email: session.user.email ?? '',
                userId: session.user.id,
                // The Admin page's gate; the database checks it again for everything an admin does.
                isAdmin: isAdmin(session.user.app_metadata),
              }
            : { status: 'signedOut' },
        )
      }
    }
    client.auth.getSession().then(({ data }) => apply(data.session))
    const { data } = client.auth.onAuthStateChange((_event, session) => apply(session))
    return () => {
      active = false
      data.subscription.unsubscribe()
    }
  }, [])

  if (!inBrowser) return { status: 'loading' }
  if (!supabase) return { status: 'unavailable' }
  return signedIn ?? { status: 'loading' }
}
