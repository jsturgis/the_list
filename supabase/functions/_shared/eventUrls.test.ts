import { assertEquals } from 'jsr:@std/assert@1.0.13'
import { checkEventUrl, isAdmin } from './eventUrls.ts'

Deno.test('takes a TicketWeb page, without its tracking', () => {
  assertEquals(checkEventUrl(' https://www.ticketweb.com/event/band-tickets/14446334?utm_medium=affiliate '), {
    ok: true,
    url: 'https://www.ticketweb.com/event/band-tickets/14446334',
    provider: 'ticketweb',
  })
})

Deno.test("takes any other site's page, keeping its query but not its fragment", () => {
  assertEquals(checkEventUrl('https://www.eventbrite.com/e/123?aff=x#tickets'), {
    ok: true,
    url: 'https://www.eventbrite.com/e/123?aff=x',
    provider: 'page',
  })
  assertEquals(checkEventUrl('https://www.bandsintown.com/e/1').ok, true)
})

Deno.test('refuses what is not a public web page', () => {
  for (const text of ['not a link', 'ftp://www.ticketweb.com/event/x', 'http://localhost:11434/api',
    'http://127.0.0.1/x', 'http://intranet/x', `https://example.com/${'a'.repeat(2000)}`]) {
    assertEquals(checkEventUrl(text).ok, false, text)
  }
})

Deno.test('admins have admin among their permissions', () => {
  assertEquals(isAdmin({ permissions: ['admin'] }), true)
  assertEquals(isAdmin({ permissions: 'admin' }), false)
  assertEquals(isAdmin({}), false)
  assertEquals(isAdmin(undefined), false)
})
