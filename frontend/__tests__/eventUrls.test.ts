import { describe, expect, it } from 'vitest'
import * as page from '@/lib/eventUrls'
import * as edgeFunction from '../../supabase/functions/_shared/eventUrls'

const LINKS = [
  'https://www.ticketweb.com/event/band-tickets/14446334?utm_medium=affiliate',
  '  https://ticketweb.com/event/x/1  ',
  'http://www.ticketweb.com/event/x/1',
  'https://www.ticketweb.com/venue/1',
  'https://www.bandsintown.com/e/1',
  'https://www.eventbrite.com/e/123?aff=x#tickets',
  'https://evil.com/ticketweb.com/event/x',
  'http://localhost:11434/api',
  'http://127.0.0.1/x',
  'http://intranet/x',
  'ftp://www.ticketweb.com/event/x',
  'not a link',
  '',
]

describe('event links', () => {
  it('takes a TicketWeb event page, without its tracking', () => {
    expect(page.checkEventUrl(LINKS[0])).toEqual({
      ok: true,
      url: 'https://www.ticketweb.com/event/band-tickets/14446334',
      provider: 'ticketweb',
    })
  })

  it("takes any other site's page, keeping its query but not its fragment", () => {
    expect(page.checkEventUrl('https://www.eventbrite.com/e/123?aff=x#tickets')).toEqual({
      ok: true,
      url: 'https://www.eventbrite.com/e/123?aff=x',
      provider: 'page',
    })
  })

  it('refuses what is not a public web page', () => {
    for (const link of ['http://localhost:11434/api', 'http://127.0.0.1/x', 'http://intranet/x', 'ftp://example.com/x']) {
      expect(page.checkEventUrl(link).ok, link).toBe(false)
    }
  })

  it('are checked the same way by the page and the admin Edge Function', () => {
    for (const link of LINKS) expect(page.checkEventUrl(link), link).toEqual(edgeFunction.checkEventUrl(link))
    expect(page.SCREENSHOT_TYPES).toEqual(edgeFunction.SCREENSHOT_TYPES)
    expect(page.SCREENSHOT_MAX_BYTES).toEqual(edgeFunction.SCREENSHOT_MAX_BYTES)
    for (const meta of [{ permissions: ['admin'] }, { permissions: [] }, {}, undefined]) {
      expect(page.isAdmin(meta)).toBe(edgeFunction.isAdmin(meta))
    }
  })
})
