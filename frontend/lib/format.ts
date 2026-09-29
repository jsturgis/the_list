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
