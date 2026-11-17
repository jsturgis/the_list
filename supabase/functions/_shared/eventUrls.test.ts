import { assertEquals } from 'jsr:@std/assert@1.0.13'
import { checkEventUrl, isAdmin } from './eventUrls.ts'

Deno.test('takes a TicketWeb event page, without its tracking', () => {
  assertEquals(checkEventUrl(' https://www.ticketweb.com/event/band-tickets/14446334?utm_medium=affiliate '), {
    ok: true,
    url: 'https://www.ticketweb.com/event/band-tickets/14446334',
    provider: 'ticketweb',
  })
})

Deno.test('refuses what it cannot read', () => {
  for (const text of ['not a link', 'ftp://www.ticketweb.com/event/x', 'https://www.ticketweb.com/venue/1',
    'https://www.bandsintown.com/e/1', 'https://evil.com/ticketweb.com/event/x']) {
    assertEquals(checkEventUrl(text).ok, false, text)
  }
})

Deno.test('admins have admin among their permissions', () => {
  assertEquals(isAdmin({ permissions: ['admin'] }), true)
  assertEquals(isAdmin({ permissions: 'admin' }), false)
  assertEquals(isAdmin({}), false)
  assertEquals(isAdmin(undefined), false)
})
