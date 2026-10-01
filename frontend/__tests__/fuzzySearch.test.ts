/**
 * Band-or-venue search tests. Keep these in step with backend/tests/test_fuzzy_search.py so the
 * browser filter and the API's `search` filter match the same Shows.
 */
import { describe, it, expect } from 'vitest'
import { fuzzyPrefixDistance, matchesSearch, normalize, tokenMatches } from '@/lib/fuzzySearch'

describe('normalize', () => {
  it.each([
    ['Café Du Nord', 'cafe du nord'],
    ['AC/DC', 'ac dc'],
    ['  The   Fox—Theater! ', 'the fox theater'],
    ['Sigur Rós', 'sigur ros'],
  ])('%s → %s', (input, expected) => {
    expect(normalize(input)).toBe(expected)
  })
})

describe('fuzzyPrefixDistance', () => {
  it.each([
    ['chapel', 'chapel', 0],
    ['chap', 'chapel', 0],
    ['chapl', 'chapel', 1],
    ['mortik', 'motrik', 1],
    ['theatre', 'theater', 1],
    ['fillmroe', 'fillmore', 1],
    ['xyz', 'chapel', 3],
  ])('%s vs %s = %i', (token, word, expected) => {
    expect(fuzzyPrefixDistance(token, word)).toBe(expected)
  })
})

describe('tokenMatches', () => {
  it('matches a substring anywhere in the name', () => {
    expect(tokenMatches('ox th', 'The Fox Theater')).toBe(true)
  })

  it('gives tokens under 5 characters no typo', () => {
    expect(tokenMatches('rose', 'Larisa Roberts')).toBe(false)
    expect(tokenMatches('chpl', 'The Chapel')).toBe(false)
  })

  it('allows 1 typo for 5–8 characters and 2 from 9', () => {
    expect(tokenMatches('chapl', 'The Chapel')).toBe(true)
    expect(tokenMatches('warfeild', 'The Warfield')).toBe(true)
    expect(tokenMatches('wrafeild', 'The Warfield')).toBe(false)
    expect(tokenMatches('muselwite', 'Charlie Musselwhite')).toBe(true)
  })
})

describe('matchesSearch', () => {
  const names = ['The Chapel', 'Rose City Band', 'Motrik']

  it('needs every word to match one of the names', () => {
    expect(matchesSearch('rose chapel', names)).toBe(true)
    expect(matchesSearch('rose fillmore', names)).toBe(false)
  })

  it('matches everything when the query is blank', () => {
    expect(matchesSearch('  ', names)).toBe(true)
  })
})
