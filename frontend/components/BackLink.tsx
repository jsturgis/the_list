'use client'

import Link from 'next/link'
import { ArrowLeftIcon } from '@heroicons/react/20/solid'
import { Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

const className = 'inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'

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

function BackInHistory({ homeHref }: { homeHref: string }) {
  const router = useRouter()
  return (
    <Link
      href={homeHref}
      className={className}
      onClick={e => {
        if (canGoBackInApp()) {
          e.preventDefault()
          router.back()
        }
      }}
    >
      <ArrowLeftIcon className="size-4 shrink-0" />
      Back
    </Link>
  )
}

function BackInHistoryWithFilters() {
  const qs = useSearchParams().toString()
  return <BackInHistory homeHref={qs ? `/?${qs}` : '/'} />
}

// Goes back in history; when there's nothing in-app to go back to (page opened directly
// or from another site), goes to the show list, keeping any filters in the URL.
// Suspense boundary lets statically prerendered pages use useSearchParams.
export default function BackLink() {
  return (
    <Suspense fallback={<BackInHistory homeHref="/" />}>
      <BackInHistoryWithFilters />
    </Suspense>
  )
}
