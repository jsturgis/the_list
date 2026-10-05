import { afterEach, describe, expect, it } from 'vitest'
import { pastShowsStyle } from '@/lib/pastShows'

const OCT_4_NOON = new Date('2026-10-04T19:00:00Z')

describe('pastShowsStyle', () => {
  it('hides every day from the export up to yesterday (Bay Area time)', () => {
    const css = pastShowsStyle('2026-10-01', OCT_4_NOON)
    for (const day of ['2026-10-01', '2026-10-02', '2026-10-03']) expect(css).toContain(`[data-show-date="${day}"]`)
    expect(css).not.toContain('2026-10-04')
    expect(css).not.toContain('2026-09-30')
  })

  it('uses the Bay Area date: 11pm Pacific on Oct 3 is still Oct 3', () => {
    const css = pastShowsStyle('2026-10-01', new Date('2026-10-04T06:00:00Z'))
    expect(css).toContain('[data-show-date="2026-10-02"]')
    expect(css).not.toContain('[data-show-date="2026-10-03"]')
  })

  it('is empty on the export day, or when the export day is unknown', () => {
    expect(pastShowsStyle('2026-10-04', OCT_4_NOON)).toBe('')
    expect(pastShowsStyle('', OCT_4_NOON)).toBe('')
  })

  it('stops after about a year of days', () => {
    expect(pastShowsStyle('2020-01-01', OCT_4_NOON).match(/data-show-date="/g)!.length).toBeLessThan(1300)
  })
})

describe('pastShowsStyle on a page', () => {
  afterEach(() => { document.head.innerHTML = ''; document.body.innerHTML = '' })

  function page(html: string) {
    document.body.innerHTML = html
    const style = document.createElement('style')
    style.textContent = pastShowsStyle('2026-10-01', OCT_4_NOON)
    document.head.append(style)
  }
  const shown = (selector: string) => getComputedStyle(document.querySelector(selector)!).display !== 'none'

  const venue = (dates: string[]) => `
    <div data-upcoming-shows>
      <section id="list" data-upcoming-shows-list>${dates.map(d => `<div id="d${d.slice(8)}" data-show-date="${d}"></div>`).join('')}</section>
      <p id="empty" data-upcoming-shows-empty style="display: none">No upcoming shows.</p>
    </div>`

  it('hides Shows that have passed and keeps the rest', () => {
    page(venue(['2026-10-03', '2026-10-04', '2026-10-05']))
    expect(shown('#d03')).toBe(false)
    expect(shown('#d04')).toBe(true)
    expect(shown('#d05')).toBe(true)
    expect(shown('#list')).toBe(true)
    expect(shown('#empty')).toBe(false)
  })

  it('hides the list and shows the empty message when every Show has passed', () => {
    page(venue(['2026-10-02', '2026-10-03']))
    expect(shown('#list')).toBe(false)
    expect(shown('#empty')).toBe(true)
  })

  it('hides a list with no empty message (a Band page) when every Show has passed', () => {
    page('<section id="list" data-upcoming-shows-list><h2>Upcoming Shows</h2><li data-show-date="2026-10-02"></li></section>')
    expect(shown('#list')).toBe(false)
  })
})
