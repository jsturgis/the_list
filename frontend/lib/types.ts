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
}

export interface Act {
  position: number
  band: Band
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
  isBenefit?: boolean
  benefitCause?: string | null
  specialEvent?: string | null
}

// ── Static JSON export (python -m app.cli export) ────────────────────────────

export type ExportVenue = Required<Venue>

export interface ExportBand extends Required<Band> {
  /** Up to six Similar Band ids, all present in the export. */
  similar: number[]
}

export interface ExportShow extends Required<Omit<Show, 'venue' | 'acts'>> {
  venueId: number
  /** [bandId, position] pairs. */
  acts: [number, number][]
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

export interface ShowFilters {
  fromDate?: string
  toDate?: string
  city?: string
  region?: string
  bandName?: string
  priceMax?: number
  isFree?: boolean
  ageRestriction?: string
  isRecommended?: boolean
}
