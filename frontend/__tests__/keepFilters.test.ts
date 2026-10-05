import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { installLinkBehaviour, keepFilters } from '@/lib/keepFilters'

function links(html: string): HTMLAnchorElement[] {
  document.body.innerHTML = html
  return [...document.querySelectorAll('a')]
}

afterEach(() => { document.body.innerHTML = '' })

describe('keepFilters', () => {
  it("gives marked links the page's query", () => {
    window.history.replaceState(null, '', '/the_list/shows/1/?region=east_bay&genre=punk')
    const [venue, back] = links(`
      <a href="/the_list/venues/2/" data-keep-filters>Venue</a>
      <a href="/the_list/" data-keep-filters data-back>Back</a>`)
    keepFilters()
    expect(venue).toHaveAttribute('href', '/the_list/venues/2/?region=east_bay&genre=punk')
    expect(back).toHaveAttribute('href', '/the_list/?region=east_bay&genre=punk')
  })

  it('leaves unmarked links alone', () => {
    window.history.replaceState(null, '', '/shows/1/?region=sf')
    const [band] = links('<a href="/bands/3/">Band</a>')
    keepFilters()
    expect(band).toHaveAttribute('href', '/bands/3/')
  })

  it('leaves hrefs unchanged when the page has no query', () => {
    const [venue] = links('<a href="/venues/2/" data-keep-filters>Venue</a>')
    keepFilters()
    expect(venue).toHaveAttribute('href', '/venues/2/')
  })

  it("replaces a marked link's own query rather than adding to it", () => {
    window.history.replaceState(null, '', '/shows/1/?free=1')
    const [venue] = links('<a href="/venues/2/?region=sf" data-keep-filters>Venue</a>')
    keepFilters()
    expect(venue).toHaveAttribute('href', '/venues/2/?free=1')
  })
})

describe('Back links', () => {
  let uninstall: () => void
  let back: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    back = vi.spyOn(window.history, 'back').mockImplementation(() => {})
    links('<a href="/" data-keep-filters data-back><svg></svg><span>Back</span></a><a href="/venues/2/">Venue</a>')
    uninstall = installLinkBehaviour()
  })
  afterEach(() => {
    uninstall()
    back.mockRestore()
    delete window.navigation
  })

  function click(target: Element, init: MouseEventInit = {}): MouseEvent {
    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init })
    target.dispatchEvent(event)
    return event
  }

  const backLink = () => document.querySelector('a[data-back] span')!

  it('goes back in history when the previous entry is on this site', () => {
    window.navigation = { canGoBack: true }
    const event = click(backLink())
    expect(back).toHaveBeenCalledOnce()
    expect(event.defaultPrevented).toBe(true)
  })

  it('follows the link to the Shows list when there is nothing on this site to go back to', () => {
    window.navigation = { canGoBack: false }
    const event = click(backLink())
    expect(back).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it('falls back to the history length without the Navigation API', () => {
    const length = vi.spyOn(window.history, 'length', 'get')
    length.mockReturnValue(1)
    expect(click(backLink()).defaultPrevented).toBe(false)
    length.mockReturnValue(3)
    expect(click(backLink()).defaultPrevented).toBe(true)
    length.mockRestore()
  })

  it('leaves modifier and middle clicks to the browser', () => {
    window.navigation = { canGoBack: true }
    for (const init of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
      expect(click(backLink(), init).defaultPrevented).toBe(false)
    }
    expect(back).not.toHaveBeenCalled()
  })

  it('ignores other links', () => {
    window.navigation = { canGoBack: true }
    expect(click(document.querySelector('a[href="/venues/2/"]')!).defaultPrevented).toBe(false)
    expect(back).not.toHaveBeenCalled()
  })
})
