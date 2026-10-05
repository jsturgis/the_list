import { href } from './basePath'
import type { ExportBand, ExportMeta, ExportShow, ExportVenue, HomePage, HomeShow, Show } from './types'

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
      .map(([bandId, position, note]) => ({ position, band: bandById.get(bandId)!, ...(note ? { note } : {}) }))
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

/** A Show trimmed to what the home page lists, filters and searches (HomeShow). */
export function toHomeShow({ venue, acts, ...show }: Show): HomeShow {
  return {
    ...show,
    venue: { id: venue.id, name: venue.name, city: venue.city, neighborhood: venue.neighborhood, region: venue.region },
    acts: acts.map(({ band, ...act }) => ({ ...act, band: { id: band.id, name: band.name, genres: band.genres } })),
  }
}

/**
 * The home page's Shows (home-shows.json): Upcoming Shows dated on or after the export's day (Bay Area time),
 * trimmed, in date then door-time order. Earlier ones have passed for good; the browser drops any that have
 * passed since.
 */
export function homeShows(shows: Show[], meta: Pick<ExportMeta, 'generatedAt'>): HomeShow[] {
  const exportDay = bayAreaToday(new Date(meta.generatedAt))
  return shows.filter(s => s.status === 'upcoming' && s.date >= exportDay).sort(byDateThenDoor).map(toHomeShow)
}

/** What the home page renders at build time: the edition, the filter options and the first `pageSize` Shows. */
export function homePage(shows: Show[], meta: ExportMeta, pageSize: number): HomePage {
  const listed = homeShows(shows, meta)
  return {
    emailSubject: meta.emailSubject,
    filterOptions: meta.filterOptions,
    totalUpcoming: meta.totalUpcoming,
    listedCount: listed.length,
    firstShows: listed.slice(0, pageSize),
  }
}

let cached: Promise<HomeShow[]> | null = null

/** Load the home page's Shows once per page load. */
export function loadHomeShows(): Promise<HomeShow[]> {
  cached ??= fetch(new URL(href('/home-shows.json'), window.location.href)).then(res => {
    if (!res.ok) throw new Error(`Couldn't load home-shows.json (${res.status})`)
    return res.json() as Promise<HomeShow[]>
  })
  cached.catch(() => { cached = null })  // let a later render retry after a failed load
  return cached
}

/** Test helper: forget the loaded Shows. */
export function resetHomeShows(): void {
  cached = null
}
