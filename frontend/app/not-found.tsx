import Link from 'next/link'
import { MusicalNoteIcon } from '@heroicons/react/24/outline'

export default function NotFound() {
  return (
    <div className="py-16 text-center flex flex-col items-center gap-3">
      <MusicalNoteIcon className="size-12 text-ink-faint" />
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="text-ink-muted">
        That show, band or venue isn&apos;t on The List, or it has dropped off since the last edition.
      </p>
      <Link href="/" className="text-link hover:underline">
        See this week&apos;s shows
      </Link>
    </div>
  )
}
