import { bayAreaToday } from './data'

/**
 * Hides Shows whose date has passed on static pages, which are built once a week. Lists of Upcoming Shows mark
 * each Show (or each date's group of Shows) with data-show-date="YYYY-MM-DD", inside a container marked
 * data-upcoming-shows. Marked elements dated before today (Bay Area time) are hidden; when none are left, the
 * container is hidden and its data-upcoming-shows-empty message, if it has one, is shown instead.
 *
 * So past Shows never flash up, the layout marks the page data-js before it renders, and CSS keeps each list
 * invisible until this has run and marked it data-upcoming-shows-ready. Without JavaScript, lists show as built.
 */
export function hidePastShows(root: ParentNode = document, today: string = bayAreaToday()): void {
  for (const list of root.querySelectorAll<HTMLElement>('[data-upcoming-shows]')) {
    let left = 0
    for (const show of list.querySelectorAll<HTMLElement>('[data-show-date]')) {
      show.hidden = (show.dataset.showDate ?? '') < today
      if (!show.hidden) left++
    }
    const empty = list.querySelector<HTMLElement>('[data-upcoming-shows-empty]')
    const shows = list.querySelector<HTMLElement>('[data-upcoming-shows-list]') ?? list
    shows.hidden = left === 0
    if (empty) empty.hidden = left > 0
    list.dataset.upcomingShowsReady = ''
  }
}
