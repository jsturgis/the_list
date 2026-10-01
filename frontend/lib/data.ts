import { withBasePath } from './basePath'
import type { ExportBand, ExportMeta, ExportShow, ExportVenue, Show, SiteData } from './types'

/** Today's date (YYYY-MM-DD) in the Bay Area, where Shows are listed by local calendar date. */
export function bayAreaToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now)
}

/** Join exported Shows with their Venue and Bands, in the shape the components already use. */
export function hydrateShows(shows: ExportShow[], venues: ExportVenue[], bands: ExportBand[]): Show[] {
  const venueById = new Map(venues.map(v => [v.id, v]))
  const bandById = new Map(bands.map(b => [b.id, b]))
  return shows.map(({ venueId, acts, ...show }) => ({
    ...show,
    venue: venueById.get(venueId)!,
    acts: acts
      .map(([bandId, position]) => ({ position, band: bandById.get(bandId)! }))
      .sort((a, b) => a.position - b.position),
  }))
}

const byDateThenDoor = (a: Show, b: Show) =>
  a.date.localeCompare(b.date) || (a.doorTime ?? '').localeCompare(b.doorTime ?? '')

/** A Band's Upcoming Shows (any Act), in date then door-time order. */
export function bandShows(shows: Show[], bandId: number): Show[] {
  return shows.filter(s => s.status === 'upcoming' && s.acts.some(a => a.band.id === bandId)).sort(byDateThenDoor)
}

/** A Band's Similar Bands, resolved in order (ids missing from the export are skipped). */
export function similarBands(band: ExportBand, bandById: Map<number, ExportBand>): ExportBand[] {
  return band.similar.map(id => bandById.get(id)).filter((b): b is ExportBand => b !== undefined)
}

async function getJson<T>(name: string): Promise<T> {
  const url = new URL(withBasePath(`/data/${name}.json`), window.location.href)
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Couldn't load ${name}.json (${res.status})`)
  return res.json() as Promise<T>
}

let cached: Promise<SiteData> | null = null

/** Load and join the exported data files once per page load. */
export function loadSiteData(): Promise<SiteData> {
  cached ??= Promise.all([
    getJson<ExportShow[]>('shows'),
    getJson<ExportVenue[]>('venues'),
    getJson<ExportBand[]>('bands'),
    getJson<ExportMeta>('meta'),
  ]).then(([shows, venues, bands, meta]) => ({
    shows: hydrateShows(shows, venues, bands),
    venues: new Map(venues.map(v => [v.id, v])),
    bands: new Map(bands.map(b => [b.id, b])),
    meta,
  }))
  cached.catch(() => { cached = null })  // let a later render retry after a failed load
  return cached
}

/** Test helper: forget the cached data. */
export function resetSiteData(): void {
  cached = null
}
