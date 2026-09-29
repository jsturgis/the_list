import { notFound } from 'next/navigation'
import { gqlClient } from '@/lib/graphql'
import { SHOW_QUERY, ALL_SHOWS_STATIC_QUERY } from '@/lib/queries'
import type { Show } from '@/lib/types'
import ShowDetail from '@/components/ShowDetail'
import BackToShows from '@/components/BackToShows'

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
  searchParams: Promise<Record<string, string | string[]>>
}

export default async function ShowPage({ params, searchParams }: PageProps) {
  const { id } = await params
  const sp = await searchParams
  const filterQs = new URLSearchParams(
    Object.fromEntries(
      Object.entries(sp).flatMap(([k, v]) => (Array.isArray(v) ? v.map(val => [k, val]) : [[k, v]]))
    )
  ).toString()

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
      <BackToShows />
      <ShowDetail show={show} filterQs={filterQs || undefined} />
    </div>
  )
}
