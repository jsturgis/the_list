/**
 * Show-filter tests, ported from the backend's show-filter GraphQL tests
 * (backend/tests/test_graphql_shows.py) so browser filtering keeps parity with the API.
 */
import { describe, it, expect } from 'vitest'
import { filterShows } from '@/lib/filterShows'
import { buildFilters } from '@/lib/filters'
import type { Show } from '@/lib/types'
import { makeBand, makeShow, makeVenue } from './fixtures'

const TODAY = '2026-10-01'
let nextId = 1

function show(overrides: Partial<Show> & { genres?: string[]; bandName?: string } = {}): Show {
  const { genres = ['rock'], bandName = `Band ${nextId}`, ...rest } = overrides
  const id = nextId++
  return makeShow({
    id, date: TODAY, doorTime: '20:00:00', status: 'upcoming', priceMin: 15, priceMax: 20, isFree: false,
    ageRestriction: '21+', acts: [{ position: 0, band: makeBand({ id, name: bandName, genres }) }],
    ...rest,
  })
}

const ids = (shows: Show[]) => shows.map(s => s.id)
const run = (shows: Show[], params: Record<string, string> = {}, today = TODAY) =>
  filterShows(shows, buildFilters(new URLSearchParams(params)), today)

describe('filterShows: defaults', () => {
  it('keeps only Upcoming Shows (not cancelled or postponed)', () => {
    const up = show(), cancelled = show({ status: 'cancelled' }), postponed = show({ status: 'postponed' })
    expect(ids(run([up, cancelled, postponed]))).toEqual([up.id])
  })

  it('drops Shows before today in Bay Area time, keeps tonight', () => {
    const yesterday = show({ date: '2026-09-30' }), tonight = show({ date: TODAY }), tomorrow = show({ date: '2026-10-02' })
    expect(ids(run([yesterday, tonight, tomorrow]))).toEqual([tonight.id, tomorrow.id])
  })

  it('orders by date then door time', () => {
    const late = show({ date: '2026-10-02', doorTime: '21:00:00' })
    const early = show({ date: '2026-10-02', doorTime: '18:00:00' })
    const first = show({ date: TODAY, doorTime: '22:00:00' })
    const noTime = show({ date: TODAY, doorTime: null })
    expect(ids(run([late, early, first, noTime]))).toEqual([noTime.id, first.id, early.id, late.id])
  })

  it('returns everything upcoming when no filters are set', () => {
    const shows = [show(), show()]
    expect(run(shows)).toHaveLength(2)
  })
})

describe('filterShows: dates (test_from_date_filter / test_to_date_filter)', () => {
  const d1 = show({ date: '2026-10-01' }), d2 = show({ date: '2026-10-02' }), d3 = show({ date: '2026-10-03' })

  it('fromDate is inclusive', () => {
    expect(ids(run([d1, d2, d3], { fromDate: '2026-10-02' }))).toEqual([d2.id, d3.id])
  })

  it('toDate is inclusive', () => {
    expect(ids(run([d1, d2, d3], { toDate: '2026-10-02' }))).toEqual([d1.id, d2.id])
  })

  it('combines into a range', () => {
    expect(ids(run([d1, d2, d3], { fromDate: '2026-10-02', toDate: '2026-10-02' }))).toEqual([d2.id])
  })
})

describe('filterShows: venue (test_region_filter)', () => {
  it('region matches exactly', () => {
    const sf = show({ venue: makeVenue({ region: 'sf' }) }), oak = show({ venue: makeVenue({ region: 'east_bay' }) })
    expect(ids(run([sf, oak], { region: 'east_bay' }))).toEqual([oak.id])
  })

  it('venue name is a case-insensitive contains', () => {
    const fox = show({ venue: makeVenue({ name: 'The Fox Theater' }) }), chapel = show({ venue: makeVenue({ name: 'The Chapel' }) })
    expect(ids(run([fox, chapel], { venue: 'fox th' }))).toEqual([fox.id])
  })
})

describe('filterShows: band (test_band_name_partial_match)', () => {
  it('band name is a case-insensitive contains on any Act', () => {
    const rose = show({ bandName: 'Rose City Band' }), motrik = show({ bandName: 'Motrik' })
    const support = show({ acts: [
      { position: 0, band: makeBand({ id: 900, name: 'Headliner' }) },
      { position: 1, band: makeBand({ id: 901, name: 'rose garden' }) },
    ] })
    expect(ids(run([rose, motrik, support], { band: 'ROSE' }))).toEqual([rose.id, support.id])
  })
})

describe('filterShows: genre (test_filter_genre_*)', () => {
  it('excludes Shows whose Bands have no genre data', () => {
    const punk = show({ genres: ['punk'] }), unknown = show({ genres: [] }), jazz = show({ genres: ['jazz'] })
    expect(ids(run([punk, unknown, jazz], { genre: 'punk' }))).toEqual([punk.id])
  })

  it('is a case-insensitive contains, like the API', () => {
    const postPunk = show({ genres: ['Post-Punk'] }), popPunk = show({ genres: ['pop punk'] }), folk = show({ genres: ['folk'] })
    expect(ids(run([postPunk, popPunk, folk], { genre: 'punk' }))).toEqual([postPunk.id, popPunk.id])
  })

  it('matches any Act, not just the headliner', () => {
    const s = show({ acts: [
      { position: 0, band: makeBand({ id: 910, name: 'Headliner', genres: [] }) },
      { position: 1, band: makeBand({ id: 911, name: 'Support', genres: ['punk'] }) },
    ] })
    expect(ids(run([s], { genre: 'punk' }))).toEqual([s.id])
  })

  it('combines with price, age and free-only', () => {
    const cheap = show({ genres: ['punk'], priceMin: 10 })
    const pricey = show({ genres: ['punk'], priceMin: 50 })
    const allAges = show({ genres: ['punk'], priceMin: 10, ageRestriction: 'a/a' })
    const free = show({ genres: ['punk'], isFree: true, priceMin: 0, priceMax: 0, ageRestriction: 'a/a' })
    const freeJazz = show({ genres: ['jazz'], isFree: true, priceMin: 0 })
    const shows = [cheap, pricey, allAges, free, freeJazz]
    expect(ids(run(shows, { genre: 'punk', priceMax: '20' }))).toEqual([cheap.id, allAges.id, free.id])
    expect(ids(run(shows, { genre: 'punk', age: 'a/a' }))).toEqual([allAges.id, free.id])
    expect(ids(run(shows, { genre: 'punk', free: '1' }))).toEqual([free.id])
  })
})

describe('filterShows: price (test_price_max_filter / test_is_free_filter)', () => {
  it('priceMax compares with the minimum price', () => {
    const a = show({ priceMin: 15, priceMax: 20 }), b = show({ priceMin: 30, priceMax: 35 }), range = show({ priceMin: 18, priceMax: 40 })
    expect(ids(run([a, b, range], { priceMax: '20' }))).toEqual([a.id, range.id])
  })

  it('priceMax drops Shows with no known price, as SQL does', () => {
    const unknown = show({ priceMin: null, priceMax: null }), known = show({ priceMin: 10 })
    expect(ids(run([unknown, known], { priceMax: '20' }))).toEqual([known.id])
  })

  it('free-only keeps free Shows', () => {
    const free = show({ isFree: true, priceMin: 0, priceMax: 0 }), paid = show({ isFree: false, priceMin: 20 })
    expect(ids(run([free, paid], { free: '1' }))).toEqual([free.id])
  })
})

describe('filterShows: age (test_age_restriction_filter)', () => {
  it('matches the age restriction exactly', () => {
    const allAges = show({ ageRestriction: 'a/a' }), over21 = show({ ageRestriction: '21+' })
    expect(ids(run([allAges, over21], { age: 'a/a' }))).toEqual([allAges.id])
  })
})
