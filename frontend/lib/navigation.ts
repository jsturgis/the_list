import { useMemo, useSyncExternalStore } from 'react'

/**
 * The site's own navigation helpers, so components don't depend on a framework's router: reading and replacing
 * the URL's query. Links and fetches build their URLs with href (lib/basePath).
 */

const listeners = new Set<() => void>()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  window.addEventListener('popstate', listener)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('popstate', listener)
  }
}

/**
 * The current URL's query, kept up to date as replaceQuery or Back/Forward change it. Empty while prerendering
 * and hydrating, so a static page and the first browser render match; the real query follows straight after.
 */
export function useQuery(): URLSearchParams {
  const search = useSyncExternalStore(subscribe, () => window.location.search, () => '')
  return useMemo(() => new URLSearchParams(search), [search])
}

/** Replace the current URL's query without adding a history entry or scrolling, and update useQuery. */
export function replaceQuery(params: URLSearchParams | string): void {
  const qs = params.toString()
  // Keep history.state: the framework's router keeps its own state there.
  window.history.replaceState(window.history.state, '', `${window.location.pathname}${qs ? `?${qs}` : ''}`)
  for (const listener of [...listeners]) listener()
}
