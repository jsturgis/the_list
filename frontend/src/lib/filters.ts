import { REGION_LABELS, ageLabel, formatDateShort } from './format'
import type { HomeShow, ShowFilters } from './types'

/** Params that `q` replaced: `band` and `venue` were separate boxes before the combined search. */
export const LEGACY_SEARCH_PARAMS = ['band', 'venue']

/** The band-or-venue search text in the URL, reading old `band`/`venue` links when there's no `q`. */
export function searchParam(params: URLSearchParams): string {
  return params.get('q') ?? LEGACY_SEARCH_PARAMS.map(k => params.get(k)).filter(Boolean).join(' ')
}

/** Every URL param the Shows filter reads (see buildFilters). */
export const FILTER_PARAMS = ['q', ...LEGACY_SEARCH_PARAMS, 'region', 'fromDate', 'toDate', 'priceMax', 'free', 'age', 'genre', 'bandId', 'venueId']

/** The params that pin the list to one Band or Venue, as a Band or Venue page's bell saves them. */
export const PIN_PARAMS = ['bandId', 'venueId']

/** The filter part of a Shows list URL's query string, as a Saved Filter stores it: other params are dropped. */
export function filterQuery(params: URLSearchParams): string {
  const kept = new URLSearchParams()
  for (const [key, value] of params) {
    if (FILTER_PARAMS.includes(key) && value.trim()) kept.append(key, value)
  }
  return kept.toString()
}

export function buildFilters(params: URLSearchParams): ShowFilters | null {
  const f: ShowFilters = {}
  const search = searchParam(params); if (search.trim()) f.search = search
  const region = params.get('region'); if (region) f.region = region
  const fromDate = params.get('fromDate'); if (fromDate) f.fromDate = fromDate
  const toDate = params.get('toDate'); if (toDate) f.toDate = toDate
  const priceMax = params.get('priceMax'); if (priceMax) f.priceMax = parseFloat(priceMax)
  if (params.get('free') === '1') f.isFree = true
  const age = params.get('age'); if (age) f.ageRestriction = age
  const genre = params.get('genre'); if (genre) f.genre = genre
  const bandId = Number(params.get('bandId')); if (bandId > 0) f.bandId = bandId
  const venueId = Number(params.get('venueId')); if (venueId > 0) f.venueId = venueId
  return Object.keys(f).length > 0 ? f : null
}

/**
 * A short name for a set of filters, suggested when saving them for an Alert:
 * "\"chapel\" · punk · SF · Free · 21+ · Up to $20 · Sat, Oct 3 – Sat, Oct 10". At most 80 characters. `pinned`
 * is the name of the Band or Venue a `bandId`/`venueId` picks, which the params alone can't tell.
 */
export function describeFilters(params: URLSearchParams, pinned?: string): string {
  const parts: string[] = []
  if (pinned && PIN_PARAMS.some(k => params.has(k))) parts.push(pinned)
  const search = searchParam(params).trim()
  if (search) parts.push(`"${search}"`)
  const genre = params.get('genre'); if (genre) parts.push(genre)
  const region = params.get('region'); if (region) parts.push(REGION_LABELS[region] ?? region)
  if (params.get('free') === '1') parts.push('Free')
  const age = params.get('age'); if (age) parts.push(ageLabel(age))
  const priceMax = params.get('priceMax'); if (priceMax) parts.push(`Up to $${priceMax}`)
  const from = params.get('fromDate'), to = params.get('toDate')
  if (from && to) parts.push(`${formatDateShort(from)} – ${formatDateShort(to)}`)
  else if (from) parts.push(`From ${formatDateShort(from)}`)
  else if (to) parts.push(`Until ${formatDateShort(to)}`)
  const name = parts.join(' · ')
  return name.length <= 80 ? name : `${name.slice(0, 79)}…`
}

/**
 * A Saved Filter's query in one canonical form, so two that select the same Shows compare equal: params in a
 * fixed order, old band/venue links read as the search they became, and search and genre in lower case (the
 * Shows filter ignores their case).
 */
export function canonicalQuery(query: string): string {
  const params = new URLSearchParams(query)
  const out: [string, string][] = []
  const search = searchParam(params).trim().toLowerCase().replace(/\s+/g, ' ')
  if (search) out.push(['q', search])
  for (const key of FILTER_PARAMS) {
    if (key === 'q' || LEGACY_SEARCH_PARAMS.includes(key)) continue
    const value = params.get(key)?.trim()
    if (value) out.push([key, key === 'genre' ? value.toLowerCase() : value])
  }
  return new URLSearchParams(out.sort(([a], [b]) => a.localeCompare(b))).toString()
}

/** The Saved Filter among `saved` that selects the same Shows as `query`, if any. */
export function findSameFilter<T extends { query: string }>(saved: T[], query: string): T | undefined {
  const target = canonicalQuery(query)
  return saved.find(f => canonicalQuery(f.query) === target)
}

/** The one Band or Venue a `bandId`/`venueId` pins the list to, named from Shows that list it, if any do. */
export interface Pinned {
  param: 'bandId' | 'venueId'
  /** Null when no listed Show has it (it has no Upcoming Shows matching the other filters). */
  name: string | null
}

export function pinnedTo(params: URLSearchParams, shows: HomeShow[]): Pinned | null {
  const filters = buildFilters(params)
  if (filters?.bandId) {
    const act = shows.flatMap(s => s.acts).find(a => a.band.id === filters.bandId)
    return { param: 'bandId', name: act?.band.name ?? null }
  }
  if (filters?.venueId) {
    return { param: 'venueId', name: shows.find(s => s.venue.id === filters.venueId)?.venue.name ?? null }
  }
  return null
}
