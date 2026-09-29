'use client'

import { useSearchParams } from 'next/navigation'

export default function BackToShows() {
  const searchParams = useSearchParams()
  const qs = searchParams.toString()
  return (
    <a
      href={qs ? `/?${qs}` : '/'}
      className="text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
    >
      ← Back to all shows
    </a>
  )
}
