import { REGION_LABELS, ageLabel, formatDateShort } from './format'
import type { ShowFilters } from './types'

/** Params that `q` replaced: `band` and `venue` were separate boxes before the combined search. */
export const LEGACY_SEARCH_PARAMS = ['band', 'venue']

/** The band-or-venue search text in the URL, reading old `band`/`venue` links when there's no `q`. */
export function searchParam(params: URLSearchParams): string {
  return params.get('q') ?? LEGACY_SEARCH_PARAMS.map(k => params.get(k)).filter(Boolean).join(' ')
}

/** Every URL param the Shows filter reads (see buildFilters). */
export const FILTER_PARAMS = ['q', ...LEGACY_SEARCH_PARAMS, 'region', 'fromDate', 'toDate', 'priceMax', 'free', 'age', 'genre']

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
  return Object.keys(f).length > 0 ? f : null
}

/**
 * A short name for a set of filters, suggested when saving them for an Alert:
 * "\"chapel\" · punk · SF · Free · 21+ · Up to $20 · Sat, Oct 3 – Sat, Oct 10". At most 80 characters.
 */
export function describeFilters(params: URLSearchParams): string {
  const parts: string[] = []
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
