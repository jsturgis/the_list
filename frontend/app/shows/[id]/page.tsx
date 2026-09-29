import { notFound } from 'next/navigation'
import { gqlClient } from '@/lib/graphql'
import { SHOW_QUERY, ALL_SHOWS_STATIC_QUERY } from '@/lib/queries'
import type { Show } from '@/lib/types'
import ShowDetail from '@/components/ShowDetail'
import Link from 'next/link'

export async function generateStaticParams() {
  try {
    const data = await gqlClient.request<{ shows: { id: number }[] }>(ALL_SHOWS_STATIC_QUERY)
    return data.shows.map(s => ({ id: String(s.id) }))
  } catch {
    return []
  }
}

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function ShowPage({ params }: PageProps) {
  const { id } = await params
  let show: Show | null = null

  try {
    const data = await gqlClient.request<{ show: Show | null }>(SHOW_QUERY, { id })
    show = data.show
  } catch {
    // fall through to notFound
  }

  if (!show) notFound()

  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/"
        className="text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
      >
        ← Back to all shows
      </Link>
      <ShowDetail show={show} />
    </div>
  )
}
