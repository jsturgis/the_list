import { useSyncExternalStore } from 'react'
import { bayAreaToday } from './data'

const noSubscription = () => () => {}

/**
 * Today's date (YYYY-MM-DD) in the Bay Area, read in the browser. Returns null while prerendering and
 * hydrating, so static pages built days earlier render the same markup, then hide past dates.
 */
export function useBayAreaToday(): string | null {
  return useSyncExternalStore(noSubscription, () => bayAreaToday(), () => null)
}
