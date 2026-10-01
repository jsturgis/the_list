import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="py-16 text-center flex flex-col items-center gap-3">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="text-zinc-500 dark:text-zinc-400">
        That show, band or venue isn&apos;t on The List, or it has dropped off since the last edition.
      </p>
      <Link href="/" className="text-amber-700 dark:text-amber-400 hover:underline">
        See this week&apos;s shows
      </Link>
    </div>
  )
}
