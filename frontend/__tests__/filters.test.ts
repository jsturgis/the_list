import { describe, expect, it } from 'vitest'
import { canonicalQuery, describeFilters, filterQuery, findSameFilter, pinnedTo } from '@/lib/filters'
import { makeBand, makeShow, makeVenue } from './fixtures'

describe('Band and Venue alerts (bandId / venueId)', () => {
  it('are kept in a Saved Filter\'s query', () => {
    expect(filterQuery(new URLSearchParams('bandId=3&utm=x'))).toBe('bandId=3')
    expect(filterQuery(new URLSearchParams('venueId=2&region=sf'))).toBe('venueId=2&region=sf')
  })

  it('compare as the same alert however they were written', () => {
    expect(canonicalQuery('venueId=2&genre=Punk')).toBe(canonicalQuery('genre=punk&venueId=2'))
    expect(findSameFilter([{ query: 'bandId=3' }, { query: 'bandId=4' }], 'bandId=4')).toEqual({ query: 'bandId=4' })
    expect(findSameFilter([{ query: 'bandId=3' }], 'venueId=3')).toBeUndefined()
  })

  it('are named after the Band or Venue', () => {
    expect(describeFilters(new URLSearchParams('bandId=3'), 'Neon Harbor')).toBe('Neon Harbor')
    expect(describeFilters(new URLSearchParams('venueId=2&genre=punk'), '924 Gilman Street')).toBe('924 Gilman Street · punk')
    expect(describeFilters(new URLSearchParams('genre=punk'), 'Neon Harbor')).toBe('punk')  // no id: the name doesn't apply
  })
})

describe('pinnedTo', () => {
  const band = makeBand({ id: 3, name: 'Neon Harbor' })
  const shows = [makeShow({ id: 1, venue: makeVenue({ id: 2, name: '924 Gilman Street' }), acts: [{ position: 1, band }] })]

  it('names the Band or Venue from the listed Shows', () => {
    expect(pinnedTo(new URLSearchParams('bandId=3'), shows)).toEqual({ param: 'bandId', name: 'Neon Harbor' })
    expect(pinnedTo(new URLSearchParams('venueId=2'), shows)).toEqual({ param: 'venueId', name: '924 Gilman Street' })
  })

  it('has no name when no Show lists it, and is null without an id', () => {
    expect(pinnedTo(new URLSearchParams('bandId=99'), [])).toEqual({ param: 'bandId', name: null })
    expect(pinnedTo(new URLSearchParams('genre=punk'), shows)).toBeNull()
  })
})
