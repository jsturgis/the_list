const DATE_LONG = new Intl.DateTimeFormat('en-US', {
  weekday: 'long', month: 'long', day: 'numeric',
})
const DATE_LONG_YEAR = new Intl.DateTimeFormat('en-US', {
  weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
})
const DATE_SHORT = new Intl.DateTimeFormat('en-US', {
  weekday: 'short', month: 'short', day: 'numeric',
})
const TIME_FMT = new Intl.DateTimeFormat('en-US', {
  hour: 'numeric', minute: '2-digit', hour12: true,
})
const USD = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD',
  minimumFractionDigits: 0, maximumFractionDigits: 0,
})

/** Display names for Region keys. */
export const REGION_LABELS: Record<string, string> = {
  sf: 'SF',
  east_bay: 'East Bay',
  north_bay: 'North Bay',
  south_bay: 'South Bay',
  santa_cruz: 'Santa Cruz',
}

const TICKET_PROVIDERS: Record<string, string> = {
  box_office: 'Box office',
  door_only: 'At the door',
  free_entry: 'Free entry',
  ticketweb: 'TicketWeb',
  seetickets: 'See Tickets',
  eventbrite: 'Eventbrite',
  bottomofthehill: 'Bottom of the Hill',
  tixr: 'Tixr',
}

/** Where tickets are sold: "box_office" -> "Box office"; an unknown one with its underscores as spaces. */
export function ticketProviderLabel(provider: string): string {
  return TICKET_PROVIDERS[provider] ?? provider.replace(/_/g, ' ')
}

/** "a/a" -> "All Ages"; other age restrictions ("21+") as they are. */
export function ageLabel(age: string): string {
  return age === 'a/a' ? 'All Ages' : age
}

function parseDate(s: string): Date {
  // Use midday to avoid DST boundary issues when converting date strings.
  return new Date(s + 'T12:00:00')
}

export function formatDateLong(dateStr: string): string {
  return DATE_LONG.format(parseDate(dateStr))
}

export function formatDateLongYear(dateStr: string): string {
  return DATE_LONG_YEAR.format(parseDate(dateStr))
}

export function formatDateShort(dateStr: string): string {
  return DATE_SHORT.format(parseDate(dateStr))
}

export function formatTime(timeStr: string | null): string | null {
  if (!timeStr) return null
  const [h, m] = timeStr.split(':').map(Number)
  return TIME_FMT.format(new Date(2000, 0, 1, h, m))
}

// Returns null when price is unknown so callers can choose their own fallback.
export function formatPrice(
  priceMin: number | null,
  priceMax: number | null,
  isFree: boolean,
): string | null {
  if (isFree) return 'Free'
  if (priceMin === null) return null
  const lo = USD.format(priceMin)
  if (priceMin === priceMax || priceMax === null) return lo
  return `${lo}–${USD.format(priceMax)}`
}

/**
 * Google Maps link for a Venue. With a place ID it opens the exact place listing
 * (query is then only a fallback); otherwise it searches the address.
 */
export function mapsHref(venue: {
  name: string
  address: string | null
  city: string
  googlePlaceId: string | null
}): string {
  const params = new URLSearchParams({ api: '1' })
  if (venue.googlePlaceId) {
    params.set('query', venue.name)
    params.set('query_place_id', venue.googlePlaceId)
  } else {
    params.set('query', venue.address ?? `${venue.name}, ${venue.city}`)
  }
  return `https://www.google.com/maps/search/?${params}`
}

/** tel: URI for a display phone number. Assumes US numbers when there's no country code. */
export function telHref(phone: string): string {
  const digits = phone.replace(/[^\d+]/g, '')
  if (digits.startsWith('+')) return `tel:${digits}`
  if (digits.length === 10) return `tel:+1${digits}`
  if (digits.length === 11 && digits.startsWith('1')) return `tel:+${digits}`
  return `tel:${digits}`
}
