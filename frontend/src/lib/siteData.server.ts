/**
 * Build-time access to the exported JSON (python -m app.cli export --out frontend/public/data).
 * Used by server components and generateStaticParams; the browser uses lib/data.ts instead.
 */
import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { bandShows, hydrateShows, similarBands } from './data'
import type { ExportBand, ExportMeta, ExportShow, ExportVenue, Show } from './types'

export interface ExportData {
  meta: ExportMeta
  show(id: number): Show | undefined
  venue(id: number): ExportVenue | undefined
  band(id: number): ExportBand | undefined
  /** A Venue's Upcoming Shows, in date then door-time order (past dates are hidden in the browser). */
  venueShows(venueId: number): Show[]
  /** A Band's Upcoming Shows, in date then door-time order (past dates are hidden in the browser). */
  bandShows(bandId: number): Show[]
  similarBands(bandId: number): ExportBand[]
  showIds(): string[]
  venueIds(): string[]
  bandIds(): string[]
}

// SITE_DATA_DIR builds the site from another export (the e2e tests use e2e/fixtures/data).
export const DEFAULT_DATA_DIR = process.env.SITE_DATA_DIR
  ? resolve(process.env.SITE_DATA_DIR)
  : join(process.cwd(), 'public', 'data')

function readJson<T>(dir: string, name: string): T {
  try {
    return JSON.parse(readFileSync(join(dir, `${name}.json`), 'utf8')) as T
  } catch (e) {
    throw new Error(
      `Missing ${name}.json in ${dir}. Export it first: python -m app.cli export --out frontend/public/data ` +
      `(${e instanceof Error ? e.message : e})`,
      { cause: e },
    )
  }
}

export function readExport(dir: string = DEFAULT_DATA_DIR): ExportData {
  const venues = readJson<ExportVenue[]>(dir, 'venues')
  const bands = readJson<ExportBand[]>(dir, 'bands')
  const shows = hydrateShows(readJson<ExportShow[]>(dir, 'shows'), venues, bands)
  const meta = readJson<ExportMeta>(dir, 'meta')

  const showById = new Map(shows.map(s => [s.id, s]))
  const venueById = new Map(venues.map(v => [v.id, v]))
  const bandById = new Map(bands.map(b => [b.id, b]))
  const byVenue = new Map<number, Show[]>()
  for (const s of shows) {
    if (s.status !== 'upcoming') continue
    byVenue.set(s.venue.id, [...(byVenue.get(s.venue.id) ?? []), s])
  }
  const byNumber = (a: string, b: string) => Number(a) - Number(b)

  return {
    meta,
    show: id => showById.get(id),
    venue: id => venueById.get(id),
    band: id => bandById.get(id),
    venueShows: venueId =>
      (byVenue.get(venueId) ?? [])
        .slice()
        .sort((a, b) => a.date.localeCompare(b.date) || (a.doorTime ?? '').localeCompare(b.doorTime ?? '')),
    bandShows: bandId => bandShows(shows, bandId),
    similarBands: bandId => {
      const band = bandById.get(bandId)
      return band ? similarBands(band, bandById) : []
    },
    showIds: () => shows.map(s => String(s.id)).sort(byNumber),
    venueIds: () => venues.map(v => String(v.id)).sort(byNumber),
    bandIds: () => bands.map(b => String(b.id)).sort(byNumber),
  }
}

let cached: ExportData | null = null

/** The export in public/data, read once per build. */
export function siteData(): ExportData {
  cached ??= readExport()
  return cached
}
