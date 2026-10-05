/**
 * Build-time access to the exported JSON (python -m app.cli export --out frontend/export). It's read only at build
 * time and isn't published with the site.
 * Used by server components and generateStaticParams; the browser uses lib/data.ts instead.
 */
import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { bandShows, exportDay, homePage, homeShows, hydrateShows, similarBands } from './data'
import type { ExportBand, ExportMeta, ExportShow, ExportVenue, HomePage, HomeShow, Show } from './types'

export interface ExportData {
  meta: ExportMeta
  /**
   * The Bay Area date the export was made ('' if unknown). Lists leave out Shows dated before it; the page hides
   * any dated before today when it loads (layouts/PastShowsStyle.astro).
   */
  exportDay: string
  show(id: number): Show | undefined
  venue(id: number): ExportVenue | undefined
  band(id: number): ExportBand | undefined
  /** A Venue's Upcoming Shows from the export's day, in date then door-time order. */
  venueShows(venueId: number): Show[]
  /** A Band's Upcoming Shows from the export's day, in date then door-time order. */
  bandShows(bandId: number): Show[]
  similarBands(bandId: number): ExportBand[]
  /** Every Upcoming Show, trimmed for the home page, in list order (home-shows.json). */
  homeShows(): HomeShow[]
  /** What the home page renders at build time, with its first `pageSize` Shows. */
  homePage(pageSize: number): HomePage
  showIds(): string[]
  venueIds(): string[]
  bandIds(): string[]
}

// SITE_DATA_DIR builds the site from another export (the e2e tests use e2e/fixtures/data).
export const DEFAULT_DATA_DIR = process.env.SITE_DATA_DIR
  ? resolve(process.env.SITE_DATA_DIR)
  : join(process.cwd(), 'export')

function readJson<T>(dir: string, name: string): T {
  try {
    return JSON.parse(readFileSync(join(dir, `${name}.json`), 'utf8')) as T
  } catch (e) {
    throw new Error(
      `Missing ${name}.json in ${dir}. Export it first: python -m app.cli export --out frontend/export ` +
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
  const from = exportDay(meta)
  const byVenue = new Map<number, Show[]>()
  for (const s of shows) {
    if (s.status !== 'upcoming' || s.date < from) continue
    byVenue.set(s.venue.id, [...(byVenue.get(s.venue.id) ?? []), s])
  }
  const byNumber = (a: string, b: string) => Number(a) - Number(b)

  return {
    meta,
    exportDay: from,
    show: id => showById.get(id),
    venue: id => venueById.get(id),
    band: id => bandById.get(id),
    venueShows: venueId =>
      (byVenue.get(venueId) ?? [])
        .slice()
        .sort((a, b) => a.date.localeCompare(b.date) || (a.doorTime ?? '').localeCompare(b.doorTime ?? '')),
    bandShows: bandId => bandShows(shows, bandId, from),
    similarBands: bandId => {
      const band = bandById.get(bandId)
      return band ? similarBands(band, bandById) : []
    },
    homeShows: () => homeShows(shows, meta),
    homePage: pageSize => homePage(shows, meta, pageSize),
    showIds: () => shows.map(s => String(s.id)).sort(byNumber),
    venueIds: () => venues.map(v => String(v.id)).sort(byNumber),
    bandIds: () => bands.map(b => String(b.id)).sort(byNumber),
  }
}

let cached: ExportData | null = null

/** The export in export/ (or SITE_DATA_DIR), read once per build. */
export function siteData(): ExportData {
  cached ??= readExport()
  return cached
}
