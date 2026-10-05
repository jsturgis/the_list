import { afterEach, describe, expect, it } from 'vitest'
import { hidePastShows } from '@/lib/upcomingShows'

afterEach(() => { document.body.innerHTML = '' })

const el = (selector: string) => document.querySelector<HTMLElement>(selector)!

describe('hidePastShows', () => {
  it('hides Shows dated before today and keeps today and later', () => {
    document.body.innerHTML = `
      <ul data-upcoming-shows>
        <li id="past" data-show-date="2026-09-30"></li>
        <li id="today" data-show-date="2026-10-01"></li>
        <li id="later" data-show-date="2026-10-04"></li>
      </ul>`
    hidePastShows(document, '2026-10-01')
    expect(el('#past').hidden).toBe(true)
    expect(el('#today').hidden).toBe(false)
    expect(el('#later').hidden).toBe(false)
    expect(el('[data-upcoming-shows]').hidden).toBe(false)
  })

  it('hides the whole list when none are left', () => {
    document.body.innerHTML = '<section data-upcoming-shows><h2>Upcoming Shows</h2><p data-show-date="2026-09-30"></p></section>'
    hidePastShows(document, '2026-10-01')
    expect(el('[data-upcoming-shows]').hidden).toBe(true)
  })

  it('shows the empty message instead of the list when none are left, and not otherwise', () => {
    const page = (date: string) => `
      <div data-upcoming-shows>
        <section data-upcoming-shows-list><div data-show-date="${date}"></div></section>
        <p data-upcoming-shows-empty hidden>No upcoming shows.</p>
      </div>`

    document.body.innerHTML = page('2026-09-30')
    hidePastShows(document, '2026-10-01')
    expect(el('[data-upcoming-shows-list]').hidden).toBe(true)
    expect(el('[data-upcoming-shows-empty]').hidden).toBe(false)
    expect(el('[data-upcoming-shows]').hidden).toBe(false)

    document.body.innerHTML = page('2026-10-02')
    hidePastShows(document, '2026-10-01')
    expect(el('[data-upcoming-shows-list]').hidden).toBe(false)
    expect(el('[data-upcoming-shows-empty]').hidden).toBe(true)
  })

  it("defaults to today's date in the Bay Area", () => {
    document.body.innerHTML = '<ul data-upcoming-shows><li id="old" data-show-date="2000-01-01"></li><li id="future" data-show-date="2999-01-01"></li></ul>'
    hidePastShows()
    expect(el('#old').hidden).toBe(true)
    expect(el('#future').hidden).toBe(false)
  })

  it('marks each list ready, so CSS stops holding it back', () => {
    document.body.innerHTML = '<ul data-upcoming-shows><li data-show-date="2026-10-02"></li></ul>'
    expect(el('[data-upcoming-shows]').dataset.upcomingShowsReady).toBeUndefined()
    hidePastShows(document, '2026-10-01')
    expect(el('[data-upcoming-shows]').dataset.upcomingShowsReady).toBe('')
  })

  it('leaves dated elements outside a marked list alone', () => {
    document.body.innerHTML = '<p id="loose" data-show-date="2000-01-01"></p>'
    hidePastShows(document, '2026-10-01')
    expect(el('#loose').hidden).toBe(false)
  })
})
