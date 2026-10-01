import type { ShowFilters } from './types'

/** Params that `q` replaced: `band` and `venue` were separate boxes before the combined search. */
export const LEGACY_SEARCH_PARAMS = ['band', 'venue']

/** The band-or-venue search text in the URL, reading old `band`/`venue` links when there's no `q`. */
export function searchParam(params: URLSearchParams): string {
  return params.get('q') ?? LEGACY_SEARCH_PARAMS.map(k => params.get(k)).filter(Boolean).join(' ')
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
