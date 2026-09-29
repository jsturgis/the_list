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
  description: string | null
  wikipediaUrl: string | null
}

export interface Band {
  id: number
  name: string
  genres: string[]
  spotifyUrl: string | null
  soundcloudUrl: string | null
  bandcampUrl: string | null
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
