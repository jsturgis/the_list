/**
 * "Add to calendar" links for a Show: a Google Calendar URL and an .ics file (as a data: URI, so it
 * works on the static site). Shows start at the door time (or set time) in Bay Area time and are
 * assumed to last 3 hours; a Show with no times becomes an all-day event.
 */
import { formatPrice, formatTime } from './format'
import type { Show } from './types'

const TIMEZONE = 'America/Los_Angeles'
const DURATION_MS = 3 * 60 * 60 * 1000
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? ''

const OFFSET_FMT = new Intl.DateTimeFormat('en-US', {
  timeZone: TIMEZONE, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric',
  hour: 'numeric', minute: 'numeric', second: 'numeric',
})

/** Bay Area wall-clock time minus UTC, in ms, at the given instant. */
function offsetAt(instant: number): number {
  const p = Object.fromEntries(OFFSET_FMT.formatToParts(new Date(instant)).map(x => [x.type, Number(x.value)]))
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - instant
}

/** The UTC instant of a Bay Area date and time ("2026-10-01", "20:00:00"). */
function bayAreaToUtc(date: string, time: string): number {
  const [y, m, d] = date.split('-').map(Number)
  const [h, min] = time.split(':').map(Number)
  const wall = Date.UTC(y, m - 1, d, h, min)
  const first = wall - offsetAt(wall)
  return wall - offsetAt(first)  // second pass settles times near a DST change
}

const utcStamp = (ms: number) => new Date(ms).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')
const dateStamp = (date: string) => date.replaceAll('-', '')
function nextDay(date: string): string {
  const [y, m, d] = date.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10)
}

interface CalendarEvent {
  title: string
  location: string
  details: string
  url: string
  /** UTC stamps (20261002T030000Z), or dates (20261001) for an all-day event. */
  start: string
  end: string
  allDay: boolean
}

function showEvent(show: Show, siteUrl: string): CalendarEvent {
  const acts = show.acts.slice().sort((a, b) => a.position - b.position).map(a => a.band.name)
  const url = `${siteUrl}/shows/${show.id}/`
  const times = [show.doorTime && `Doors ${formatTime(show.doorTime)}`, show.setTime && `Set ${formatTime(show.setTime)}`]
    .filter(Boolean).join(' · ')
  const price = formatPrice(show.priceMin, show.priceMax, show.isFree)
  const age = show.ageRestriction === 'a/a' ? 'All Ages' : show.ageRestriction
  const details = [acts.join(', '), times, [price, age].filter(Boolean).join(' · '), url].filter(Boolean).join('\n')

  const time = show.doorTime ?? show.setTime
  const startMs = time ? bayAreaToUtc(show.date, time) : null
  return {
    title: `${acts[0] ?? 'Show'} at ${show.venue.name}`,
    location: [show.venue.name, show.venue.address ?? show.venue.city].filter(Boolean).join(', '),
    details,
    url,
    start: startMs !== null ? utcStamp(startMs) : dateStamp(show.date),
    end: startMs !== null ? utcStamp(startMs + DURATION_MS) : dateStamp(nextDay(show.date)),
    allDay: startMs === null,
  }
}

export function googleCalendarUrl(show: Show, siteUrl: string = SITE_URL): string {
  const e = showEvent(show, siteUrl)
  const params = new URLSearchParams({
    action: 'TEMPLATE', text: e.title, dates: `${e.start}/${e.end}`, details: e.details, location: e.location,
  })
  return `https://calendar.google.com/calendar/render?${params}`
}

const escapeText = (s: string) => s.replace(/\\/g, '\\\\').replace(/;/g, '\;').replace(/,/g, '\\,').replace(/\n/g, '\\n')

const utf8 = new TextEncoder()

/** Lines longer than 75 bytes continue on the next line after a space (RFC 5545), never mid-character. */
function fold(line: string): string {
  const parts: string[] = []
  let current = ''
  let bytes = 0
  for (const char of line) {
    const size = utf8.encode(char).length
    if (bytes + size > 75) {
      parts.push(current)
      current = ' '
      bytes = 1
    }
    current += char
    bytes += size
  }
  parts.push(current)
  return parts.join('\r\n')
}

export function icsDataUri(show: Show, siteUrl: string = SITE_URL, now: Date = new Date()): string {
  const e = showEvent(show, siteUrl)
  const when = e.allDay
    ? [`DTSTART;VALUE=DATE:${e.start}`, `DTEND;VALUE=DATE:${e.end}`]
    : [`DTSTART:${e.start}`, `DTEND:${e.end}`]
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//The List//Show//EN', 'BEGIN:VEVENT',
    `UID:show-${show.id}@the-list`, `DTSTAMP:${utcStamp(now.getTime())}`, ...when,
    `SUMMARY:${escapeText(e.title)}`, `LOCATION:${escapeText(e.location)}`, `DESCRIPTION:${escapeText(e.details)}`,
    `URL:${e.url}`, 'END:VEVENT', 'END:VCALENDAR',
  ]
  return 'data:text/calendar;charset=utf-8,' + encodeURIComponent(lines.map(fold).join('\r\n') + '\r\n')
}

/** "deafheaven-2026-10-01.ics" */
export function icsFilename(show: Show): string {
  const headliner = show.acts.slice().sort((a, b) => a.position - b.position)[0]?.band.name ?? 'show'
  const slug = headliner.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'show'
  return `${slug}-${show.date}.ics`
}
