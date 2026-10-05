/**
 * Plain-DOM behaviour for static pages, so their links don't need React:
 * - Links marked data-keep-filters get the page's query string, so the Shows list's filters follow the
 *   visitor from page to page (a Show page opened from a filtered list links to its Venue with those filters).
 * - A plain click on a link marked data-back goes back in history when the previous entry is on this site;
 *   otherwise the link is followed (to the Shows list, with the filters kept).
 */

// Navigation API isn't in TypeScript's DOM lib yet.
declare global {
  interface Window {
    navigation?: { canGoBack: boolean }
  }
}

/** Give every link marked data-keep-filters the current page's query string (replacing any it had). */
export function keepFilters(root: ParentNode = document): void {
  const search = window.location.search
  for (const link of root.querySelectorAll<HTMLAnchorElement>('a[data-keep-filters]')) {
    const url = new URL(link.getAttribute('href') ?? '', window.location.href)
    url.search = search
    link.setAttribute('href', `${url.pathname}${url.search}${url.hash}`)
  }
}

// True only if the previous history entry is a page on this site. Falls back to
// history.length (which also counts other sites) where the Navigation API is missing.
function canGoBackInApp(): boolean {
  if (window.navigation) return window.navigation.canGoBack
  return window.history.length > 1
}

function onClick(e: MouseEvent): void {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  const link = e.target instanceof Element ? e.target.closest('a[data-back]') : null
  if (link && canGoBackInApp()) {
    e.preventDefault()
    window.history.back()
  }
}

/** Run keepFilters on the page and handle Back links. Returns a function that removes the click handler. */
export function installLinkBehaviour(doc: Document = document): () => void {
  keepFilters(doc)
  doc.addEventListener('click', onClick)
  return () => doc.removeEventListener('click', onClick)
}
