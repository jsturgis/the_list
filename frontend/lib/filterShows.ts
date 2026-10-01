import { bayAreaToday } from './data'
import { matchesSearch } from './fuzzySearch'
import type { Show, ShowFilters } from './types'

const contains = (text: string, needle: string) => text.toLowerCase().includes(needle.toLowerCase())

/**
 * The home page's Show filter. Mirrors the API's show query (backend `_query_shows`) so browser
 * filtering gives the same results: Upcoming Shows from today (Bay Area time), then each filter.
 * Returns Shows in date, then door-time, order.
 */
export function filterShows(shows: Show[], filters: ShowFilters | null, today: string = bayAreaToday()): Show[] {
  const f = filters ?? {}
  return shows
    .filter(s => {
      if (s.status !== 'upcoming' || s.date < today) return false
      if (f.fromDate && s.date < f.fromDate) return false
      if (f.toDate && s.date > f.toDate) return false
      if (f.region && s.venue.region !== f.region) return false
      if (f.search && !matchesSearch(f.search, [s.venue.name, ...s.acts.map(a => a.band.name)])) return false
      // Any genre of any Act; Shows with no genre data can't match.
      if (f.genre && !s.acts.some(a => a.band.genres.some(g => contains(g, f.genre!)))) return false
      // Compared with the minimum price; an unknown price never matches (as with SQL NULL).
      if (f.priceMax !== undefined && !(s.priceMin !== null && s.priceMin <= f.priceMax)) return false
      if (f.isFree && !s.isFree) return false
      if (f.ageRestriction && s.ageRestriction !== f.ageRestriction) return false
      return true
    })
    .sort((a, b) => a.date.localeCompare(b.date) || (a.doorTime ?? '').localeCompare(b.doorTime ?? ''))
}
