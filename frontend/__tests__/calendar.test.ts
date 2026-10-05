import { describe, it, expect } from 'vitest'
import { googleCalendarUrl, icsFilename, icsHref, icsText } from '@/lib/calendar'
import { makeBand, makeShow, makeVenue } from './fixtures'

const SITE = 'https://jsturgis.github.io/the_list'
const show = makeShow({
  id: 42,
  date: '2026-10-01',
  doorTime: '20:00:00',
  setTime: '21:00:00',
  priceMin: 15, priceMax: 18, isFree: false, ageRestriction: 'a/a',
  venue: makeVenue({ name: 'Bottom of the Hill', address: '1233 17th St, San Francisco, CA 94107', city: 'San Francisco' }),
  acts: [
    { position: 0, band: makeBand({ id: 1, name: 'Deafheaven' }) },
    { position: 1, band: makeBand({ id: 2, name: 'Uniform' }) },
  ],
})
const google = (s = show) => new URL(googleCalendarUrl(s, SITE))
const ics = (s = show) => icsText(s, SITE, new Date('2026-09-30T12:00:00Z'))

describe('googleCalendarUrl', () => {
  it('creates an event from the door time, in UTC, lasting 3 hours', () => {
    const url = google()
    expect(url.origin + url.pathname).toBe('https://calendar.google.com/calendar/render')
    expect(url.searchParams.get('action')).toBe('TEMPLATE')
    // 8pm PDT on Oct 1 is 03:00 UTC on Oct 2.
    expect(url.searchParams.get('dates')).toBe('20261002T030000Z/20261002T060000Z')
  })

  it('follows daylight saving time', () => {
    // 8pm PST on Nov 6 (after DST ends) is 04:00 UTC on Nov 7.
    expect(google(makeShow({ ...show, date: '2026-11-06' })).searchParams.get('dates')).toBe('20261107T040000Z/20261107T070000Z')
  })

  it('names the headliner and venue, with the address and lineup', () => {
    const url = google()
    expect(url.searchParams.get('text')).toBe('Deafheaven at Bottom of the Hill')
    expect(url.searchParams.get('location')).toBe('Bottom of the Hill, 1233 17th St, San Francisco, CA 94107')
    const details = url.searchParams.get('details')!
    expect(details).toContain('Deafheaven, Uniform')
    expect(details).toContain('Doors 8:00 PM · Set 9:00 PM')
    expect(details).toContain(`${SITE}/shows/42/`)
  })

  it('uses the set time when there is no door time', () => {
    expect(google(makeShow({ ...show, doorTime: null })).searchParams.get('dates')).toBe('20261002T040000Z/20261002T070000Z')
  })

  it('makes an all-day event when the show has no times', () => {
    expect(google(makeShow({ ...show, doorTime: null, setTime: null })).searchParams.get('dates')).toBe('20261001/20261002')
  })
})

describe('icsText', () => {
  it('is a calendar file with one event at the right UTC times', () => {
    const text = ics()
    expect(text).toMatch(/^BEGIN:VCALENDAR\r\n/)
    expect(text).toContain('\r\nBEGIN:VEVENT\r\n')
    expect(text).toContain('\r\nUID:show-42@the-list\r\n')
    expect(text).toContain('\r\nDTSTAMP:20260930T120000Z\r\n')
    expect(text).toContain('\r\nDTSTART:20261002T030000Z\r\n')
    expect(text).toContain('\r\nDTEND:20261002T060000Z\r\n')
    expect(text).toContain('\r\nSUMMARY:Deafheaven at Bottom of the Hill\r\n')
    expect(text).toContain(`\r\nURL:${SITE}/shows/42/\r\n`)
    expect(text).toMatch(/END:VEVENT\r\nEND:VCALENDAR\r\n$/)
  })

  it('escapes commas, semicolons and new lines in text', () => {
    expect(ics()).toContain('LOCATION:Bottom of the Hill\\, 1233 17th St\\, San Francisco\\, CA 94107')
    expect(ics()).toMatch(/DESCRIPTION:.*\\n/)
    const semicolon = makeShow({ ...show, acts: [{ position: 0, band: makeBand({ name: 'Rock; Roll' }) }] })
    expect(ics(semicolon)).toContain('Rock\\; Roll')
  })

  it('folds lines longer than 75 bytes, without splitting characters', () => {
    const long = makeShow({ ...show, notes: null, acts: [{ position: 0, band: makeBand({ name: 'Señor · Ñandú '.repeat(8) }) }] })
    const lines = ics(long).split('\r\n')
    for (const line of lines) expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75)
    expect(lines.join('\r\n').replace(/\r\n /g, '')).toContain('Señor · Ñandú Señor')
  })

  it('uses all-day dates when the show has no times', () => {
    const text = ics(makeShow({ ...show, doorTime: null, setTime: null }))
    expect(text).toContain('\r\nDTSTART;VALUE=DATE:20261001\r\n')
    expect(text).toContain('\r\nDTEND;VALUE=DATE:20261002\r\n')
  })
})

describe('icsFilename', () => {
  it('names the file after the headliner and date', () => {
    expect(icsFilename(show)).toBe('deafheaven-2026-10-01.ics')
  })
})

describe('icsHref', () => {
  it("is the Show's static .ics file, outside the Show pages", () => {
    expect(icsHref(42)).toBe('/calendar/42.ics')
  })
})
