'use client'

import { ArrowLeftIcon } from '@heroicons/react/20/solid'
import { href } from '@/lib/basePath'
import { useQuery } from '@/lib/navigation'

const className = 'inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink-soft'

// Navigation API isn't in TypeScript's DOM lib yet.
declare global {
  interface Window {
    navigation?: { canGoBack: boolean }
  }
}

// True only if the previous history entry is a page on this site. Falls back to
// history.length (which also counts other sites) where the Navigation API is missing.
function canGoBackInApp(): boolean {
  if (window.navigation) return window.navigation.canGoBack
  return window.history.length > 1
}

// Goes back in history; when there's nothing in-app to go back to (page opened directly
// or from another site), goes to the show list, keeping any filters in the URL.
export default function BackLink() {
  const qs = useQuery().toString()
  return (
    <a
      href={href(qs ? `/?${qs}` : '/')}
      className={className}
      onClick={e => {
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
        if (canGoBackInApp()) {
          e.preventDefault()
          window.history.back()
        }
      }}
    >
      <ArrowLeftIcon className="size-4 shrink-0" />
      Back
    </a>
  )
}
