'use client'

import Link from 'next/link'
import { useContext, useEffect, useState } from 'react'
import type { Band } from '@/lib/types'
import { gqlClient } from '@/lib/graphql'
import { SIMILAR_BANDS_QUERY } from '@/lib/queries'
import { InModalContext } from './Modal'

interface SimilarBandsProps {
  bandId: number
}

export default function SimilarBands({ bandId }: SimilarBandsProps) {
  const inModal = useContext(InModalContext)
  const [bands, setBands] = useState<Band[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    gqlClient
      .request<{ similarBands: Band[] }>(SIMILAR_BANDS_QUERY, { bandId: String(bandId), k: 6 })
      .then(data => { if (!cancelled) setBands(data.similarBands) })
      .catch(() => { if (!cancelled) setBands([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [bandId])

  if (loading || bands.length === 0) return null

  return (
    <section data-testid="similar-bands">
      <h2 className="text-base font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
        Similar Bands
      </h2>
      <ul className="flex flex-col gap-1">
        {bands.map(b => (
          <li key={b.id}>
            <Link
              href={`/bands/${b.id}`}
              replace={inModal}
              className="flex items-center gap-2 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800 -mx-2 px-2 py-1 rounded"
            >
              <span className="font-medium text-zinc-900 dark:text-zinc-50">{b.name}</span>
              {b.genres.length > 0 && (
                <span className="text-zinc-400 dark:text-zinc-500 text-xs">
                  {b.genres.slice(0, 2).join(', ')}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
