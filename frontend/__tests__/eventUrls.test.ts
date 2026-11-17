import { describe, expect, it } from 'vitest'
import * as page from '@/lib/eventUrls'
import * as edgeFunction from '../../supabase/functions/_shared/eventUrls'

const LINKS = [
  'https://www.ticketweb.com/event/band-tickets/14446334?utm_medium=affiliate',
  '  https://ticketweb.com/event/x/1  ',
  'http://www.ticketweb.com/event/x/1',
  'https://www.ticketweb.com/venue/1',
  'https://www.bandsintown.com/e/1',
  'https://evil.com/ticketweb.com/event/x',
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

  it('sends Bandsintown links to screenshots', () => {
    expect(page.checkEventUrl('https://www.bandsintown.com/e/1')).toMatchObject({ ok: false, reason: expect.stringMatching(/screenshot/) })
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
