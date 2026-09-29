'use client'

export default function BackToShows() {
  const qs = typeof window !== 'undefined' ? window.location.search : ''
  return (
    <a
      href={`/${qs}`}
      className="text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
    >
      ← Back to all shows
    </a>
  )
}
