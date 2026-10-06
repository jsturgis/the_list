import { ArrowDownTrayIcon, CalendarDaysIcon, StarIcon } from '@heroicons/react/16/solid'
import { Flags, StatusBadge } from './ShowBadges'
import type { HomeShow } from '@/lib/types'
import { ageLabel, formatDateCompact, formatPrice, formatTime } from '@/lib/format'
import { googleCalendarUrl, icsFilename, icsHref } from '@/lib/calendar'
import { href } from '@/lib/basePath'

interface ShowRowProps {
  show: HomeShow
  /** The Shows list's filters, carried to the Show page. */
  filterQs?: string
  /** Hide the Venue line, e.g. on that Venue's own page. */
  showVenue?: boolean
  /** The headliner's heading level: one below the list's date headings, or the section's. */
  headingLevel?: 3 | 4
  /** Start the row with its compact date ("SAT / OCT 3"), for lists without date headings (Venue and Band pages). */
  showDate?: boolean
}

const calendarLink =
  'inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs text-ink-muted hover:bg-muted hover:text-link ' +
  'outline-none focus-visible:ring-2 focus-visible:ring-focus-ring'

/**
 * A Show in a list (DESIGN.md, "Show list item"): the headliner "with" the supports, then Venue · city; then door
 * time · price · age, the flags and, for Upcoming Shows, links to add it to a calendar. On phones each part is its
 * own line; from `sm` the details sit in a right-hand column. The headliner is the link to the Show page, stretched
 * over the whole row; the calendar links sit above it.
 */
export default function ShowRow({ show, filterQs = '', showVenue = true, headingLevel = 3, showDate = false }: ShowRowProps) {
  const Heading = `h${headingLevel}` as const
  const headliner = show.acts[0]?.band
  const supports = show.acts.slice(1).map(a => a.band.name)
  const details = [formatTime(show.doorTime), formatPrice(show.priceMin, show.priceMax, show.isFree), ageLabel(show.ageRestriction)]
    .filter(Boolean)
    .join(' · ')

  const date = showDate ? formatDateCompact(show.date) : null
  return (
    <div
      data-recommended={show.isRecommended ? '' : undefined}
      className={`relative flex gap-3 px-4 py-3 transition-colors has-[[data-show-link]:focus-visible]:ring-2 has-[[data-show-link]:focus-visible]:ring-inset has-[[data-show-link]:focus-visible]:ring-focus-ring ${
        show.isRecommended ? 'bg-pick hover:bg-pick-hover' : 'hover:bg-surface-hover'
      }`}
    >
      {date && (
        <time dateTime={show.date} className="flex w-12 shrink-0 flex-col items-center pt-0.5 leading-tight uppercase">
          <span className="text-[11px] font-semibold tracking-wide text-ink-muted">{date.weekday}</span>
          <span className="whitespace-nowrap text-sm font-bold text-ink">{date.monthDay}</span>
        </time>
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={show.status} size="compact" />
            <Heading className="text-base leading-snug text-ink-muted">
              {show.isRecommended && <StarIcon aria-hidden="true" className="inline size-4 -mt-0.5 mr-1 text-pick-line" />}
              <a
                href={href(filterQs ? `/shows/${show.id}/?${filterQs}` : `/shows/${show.id}/`)}
                data-show-link=""
                className="font-bold text-ink outline-none after:absolute after:inset-0 after:content-['']"
              >
                {show.isRecommended && <span className="sr-only">Steve&apos;s pick: </span>}
                {headliner?.name ?? 'Show'}
              </a>
              {supports.length > 0 && <> with {supports.join(', ')}</>}
            </Heading>
          </div>
          {showVenue && <p className="mt-0.5 text-sm text-ink-soft">{show.venue.name} · {show.venue.city}</p>}
        </div>

        {/* Phone: details, flags, calendar links, one per line (order-*). From sm: details and calendar icons on one
            line in a right-hand column, flags below. */}
        <div className="flex flex-col gap-1 sm:w-64 sm:shrink-0 sm:items-end sm:text-right">
          <div className="contents sm:order-1 sm:flex sm:items-center sm:justify-end sm:gap-2">
            {details && <span className="order-1 text-xs text-ink-muted sm:text-sm sm:text-ink-soft">{details}</span>}
            {show.status === 'upcoming' && (
              <span className="relative z-10 order-3 -ml-2 flex items-center gap-1 sm:-my-1 sm:-mr-2 sm:ml-0">
                <a href={icsHref(show.id)} download={icsFilename(show)} aria-label="Add to calendar (.ics)"
                   title="Add to calendar (.ics)" className={calendarLink}>
                  <ArrowDownTrayIcon aria-hidden="true" className="size-4" />
                  <span className="sm:sr-only">.ics</span>
                </a>
                <a href={googleCalendarUrl(show)} target="_blank" rel="noopener noreferrer"
                   aria-label="Add to Google Calendar" title="Add to Google Calendar" className={calendarLink}>
                  <CalendarDaysIcon aria-hidden="true" className="size-4" />
                  <span className="sm:sr-only">Google Calendar</span>
                </a>
              </span>
            )}
          </div>
          <div className="order-2 empty:hidden sm:flex sm:justify-end">
            <Flags show={show} size="compact" />
          </div>
        </div>
      </div>
    </div>
  )
}
