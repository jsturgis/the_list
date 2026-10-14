import { describe, expect, it } from 'vitest'
import { inSitemap } from '@/lib/sitemap'

describe('inSitemap', () => {
  it('lists pages at their slugs', () => {
    expect(inSitemap('https://list.sturgis.me/')).toBe(true)
    expect(inSitemap('https://list.sturgis.me/bands/neon-harbor/')).toBe(true)
    expect(inSitemap('https://list.sturgis.me/bands/band-311/')).toBe(true)
    expect(inSitemap('https://list.sturgis.me/venues/924-gilman-street/')).toBe(true)
    expect(inSitemap('https://list.sturgis.me/shows/neon-harbor-2026-10-03/')).toBe(true)
  })

  it('leaves out the numeric URLs, which redirect to the slugs', () => {
    expect(inSitemap('https://list.sturgis.me/bands/1/')).toBe(false)
    expect(inSitemap('https://jsturgis.github.io/the_list/bands/1001/')).toBe(false)
    expect(inSitemap('https://list.sturgis.me/venues/2/')).toBe(false)
    expect(inSitemap('https://list.sturgis.me/shows/102/')).toBe(false)
  })

  it('leaves out the Unsubscribe page, which is noindex', () => {
    expect(inSitemap('https://list.sturgis.me/alerts/unsubscribe/')).toBe(false)
  })
})
