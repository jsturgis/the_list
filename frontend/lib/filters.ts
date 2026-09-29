export function buildFilters(params: URLSearchParams): Record<string, unknown> | null {
  const f: Record<string, unknown> = {}
  const band = params.get('band'); if (band) f.bandName = band
  const venue = params.get('venue'); if (venue) f.venueName = venue
  const region = params.get('region'); if (region) f.region = region
  const fromDate = params.get('fromDate'); if (fromDate) f.fromDate = fromDate
  const toDate = params.get('toDate'); if (toDate) f.toDate = toDate
  const priceMax = params.get('priceMax'); if (priceMax) f.priceMax = parseFloat(priceMax)
  if (params.get('free') === '1') f.isFree = true
  const age = params.get('age'); if (age) f.ageRestriction = age
  const genre = params.get('genre'); if (genre) f.genre = genre
  return Object.keys(f).length > 0 ? f : null
}
