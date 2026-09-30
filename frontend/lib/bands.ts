import { gqlClient } from '@/lib/graphql'
import { BAND_QUERY, BAND_SHOWS_QUERY, ALL_BANDS_STATIC_QUERY } from '@/lib/queries'
import type { Band, Show } from '@/lib/types'

export async function bandStaticParams() {
  try {
    const data = await gqlClient.request<{ shows: { acts: { band: { id: number } }[] }[] }>(
      ALL_BANDS_STATIC_QUERY,
    )
    const ids = new Set<number>()
    for (const show of data.shows) {
      for (const act of show.acts) {
        ids.add(act.band.id)
      }
    }
    return Array.from(ids).map(id => ({ id: String(id) }))
  } catch {
    return []
  }
}

export async function loadBand(id: string): Promise<{ band: Band; upcomingShows: Show[] } | null> {
  try {
    const bandData = await gqlClient.request<{ band: Band | null }>(BAND_QUERY, { id })
    const band = bandData.band
    if (!band) return null
    const showsData = await gqlClient.request<{ shows: Show[] }>(BAND_SHOWS_QUERY, {
      bandId: band.id,
    })
    return { band, upcomingShows: showsData.shows }
  } catch {
    return null
  }
}
