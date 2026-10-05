export interface Venue {
  id: number
  name: string
  address: string | null
  city: string
  region: string
  websiteUrl: string | null
  latitude: number | null
  longitude: number | null
  timezone: string | null
  phone: string | null
  googleRating: number | null
  googlePlaceId: string | null
  description: string | null
  wikipediaUrl: string | null
  // From the formatted edition (present in the exported data; not requested by every GraphQL query)
  neighborhood?: string | null
  venueType?: string | null
  nearestTransit?: string | null
  instagram?: string | null
  imageUrl?: string | null
  defaultAgeRestriction?: string | null
  isSoberSpace?: boolean | null
  isCashOnly?: boolean | null
  membershipRequired?: boolean | null
}

export interface Band {
  id: number
  name: string
  genres: string[]
  spotifyUrl: string | null
  soundcloudUrl: string | null
  bandcampUrl: string | null
  // From the formatted edition
  websiteUrl?: string | null
  imageUrl?: string | null
  isLocal?: boolean | null
  // From the enriched export
  description?: string | null
}

export interface Act {
  position: number
  band: Band
  /** What Steve put in parentheses after the name, e.g. the members. */
  note?: string
}

export interface Show {
  id: number
  date: string
  doorTime: string | null
  setTime: string | null
  venue: Venue
  acts: Act[]
  priceMin: number | null
  priceMax: number | null
  isFree: boolean
  ageRestriction: string
  status: string
  isRecommended: boolean
  willSellOut: boolean
  isPit: boolean
  isDrinkTickets: boolean
  isNoReentry: boolean
  notes: string | null
  // From the formatted edition
  isMatinee?: boolean
  isSoldOut?: boolean
  ticketProvider?: string | null
  ticketUrl?: string | null
  isBenefit?: boolean
  benefitCause?: string | null
  specialEvent?: string | null
}

/**
 * A Show as a Show card or row lists it: the Show's own fields, with just enough of its Venue and Bands to name
 * them. Islands get these rather than full Shows, so a page doesn't serialise every Venue and Band description.
 */
export type ShowSummary = Omit<Show, 'venue' | 'acts'> & {
  venue: Pick<Venue, 'id' | 'name' | 'city' | 'neighborhood'>
  acts: (Omit<Act, 'band'> & { band: Pick<Band, 'id' | 'name'> })[]
}

// ── Static JSON export (python -m app.cli export) ────────────────────────────

export type ExportVenue = Required<Venue>

export interface ExportBand extends Required<Band> {
  /** Up to six Similar Band ids, all present in the export. */
  similar: number[]
}

export interface ExportShow extends Required<Omit<Show, 'venue' | 'acts'>> {
  venueId: number
  /** [bandId, position], plus the act's note when it has one. */
  acts: ([number, number] | [number, number, string])[]
}

export interface ExportMeta {
  generatedAt: string
  emailSubject: string | null
  filterOptions: { regions: string[]; ages: string[]; genres: string[]; dates: string[] }
  totalUpcoming: number
}

export interface SiteData {
  shows: Show[]
  bands: Map<number, ExportBand>
  venues: Map<number, ExportVenue>
  meta: ExportMeta
}

/** Filters parsed from the home page URL (see lib/filters.ts buildFilters). */
export interface ShowFilters {
  fromDate?: string
  toDate?: string
  region?: string
  /** Fuzzy band-or-venue search (see lib/fuzzySearch.ts). */
  search?: string
  genre?: string
  priceMax?: number
  isFree?: boolean
  ageRestriction?: string
}
