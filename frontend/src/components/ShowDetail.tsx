import type { Show } from '@/lib/types'
import { formatTime, formatPrice, formatDateLongYear, mapsHref } from '@/lib/format'
import { ArrowDownTrayIcon, BuildingOffice2Icon, CalendarDaysIcon, CalendarIcon, ClockIcon, GlobeAltIcon, MapPinIcon, ShoppingCartIcon, SparklesIcon, TicketIcon, UserIcon } from '@heroicons/react/20/solid'
import { googleCalendarUrl, icsDataUri, icsFilename } from '@/lib/calendar'
import BandLink from './BandLink'
import ExternalLink from './ExternalLink'
import { Flags, StatusBadge } from './ShowBadges'
import VenueLink from './VenueLink'

function formatAge(age: string): string {
  if (age === 'a/a') return 'All Ages'
  return age
}

/**
 * Whether to name the ticket provider. The provider and the link can come from different exports, so a
 * link names its provider only when it goes to that provider's site ("ticketweb" → www.ticketweb.com).
 */
function ticketProviderMatches(show: Show): boolean {
  if (!show.ticketProvider) return false
  if (!show.ticketUrl) return true
  const provider = show.ticketProvider.toLowerCase().replace(/[^a-z0-9]/g, '')
  try {
    return new URL(show.ticketUrl).hostname.replace(/\./g, '').includes(provider)
  } catch {
    return false
  }
}

interface ShowDetailProps {
  show: Show
}

export default function ShowDetail({ show }: ShowDetailProps) {
  const door = formatTime(show.doorTime)
  const set = formatTime(show.setTime)
  const price = formatPrice(show.priceMin, show.priceMax, show.isFree) ?? 'TBA'
  const age = formatAge(show.ageRestriction)
  const ticketsLabel = ticketProviderMatches(show) ? `Tickets via ${show.ticketProvider}` : 'Tickets'

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      <StatusBadge status={show.status} size="detail" />

      <header>
        {show.specialEvent && (
          <div
            role="note"
            aria-label="Special event"
            className="flex items-center gap-2 mb-4 px-4 py-2.5 rounded-lg border border-accent-soft-line bg-accent-soft text-accent-soft-ink"
          >
            <SparklesIcon className="size-5 shrink-0 text-link" />
            <span className="font-semibold">{show.specialEvent}</span>
          </div>
        )}
        <div className="flex items-center gap-1.5 text-sm text-ink-muted mb-1">
          <CalendarIcon className="size-4 shrink-0" />
          <span>{formatDateLongYear(show.date)}</span>
          {show.status === 'upcoming' && (
            <span className="flex items-center ml-1">
              <a
                href={icsDataUri(show)}
                download={icsFilename(show)}
                aria-label="Add to calendar"
                title="Add to calendar (.ics)"
                className="p-1 rounded hover:text-link hover:bg-muted"
              >
                <ArrowDownTrayIcon className="size-4" />
              </a>
              <a
                href={googleCalendarUrl(show)}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Add to Google Calendar"
                title="Add to Google Calendar"
                className="p-1 rounded hover:text-link hover:bg-muted"
              >
                <CalendarDaysIcon className="size-4" />
              </a>
            </span>
          )}
        </div>
        <h1 className="text-3xl font-bold text-ink">
          {show.acts[0]?.band.name ?? 'Unknown'}
        </h1>
        <p className="text-lg text-ink-soft mt-1">
          at <VenueLink venueId={show.venue.id} className="hover:underline">{show.venue.name}</VenueLink> · {show.venue.city}
        </p>
      </header>

      <section className="flex flex-wrap gap-4 text-sm text-ink-soft">
        {door && (
          <div className="flex items-center gap-1.5">
            <ClockIcon className="size-4 shrink-0 text-ink-faint" />
            <span className="font-medium">Doors: </span>
            {door}
            {set && <> / Set: {set}</>}
          </div>
        )}
        <div className="flex items-center gap-1.5">
          <TicketIcon className="size-4 shrink-0 text-ink-faint" />
          <span className="font-medium">Price: </span>
          {price}
        </div>
        <div className="flex items-center gap-1.5">
          <UserIcon className="size-4 shrink-0 text-ink-faint" />
          <span className="font-medium">Ages: </span>
          {age}
        </div>
        {(show.ticketUrl || show.ticketProvider) && (
          <div className="flex items-center gap-1.5">
            <ShoppingCartIcon className="size-4 shrink-0 text-ink-faint" />
            {show.ticketUrl ? (
              <ExternalLink href={show.ticketUrl} className="text-link hover:underline">
                {ticketsLabel}
              </ExternalLink>
            ) : ticketsLabel}
          </div>
        )}
      </section>

      <Flags show={show} size="detail" showBenefitCause />

      <section>
        <h2 className="text-base font-semibold mb-3 text-ink">Lineup</h2>
        <ol className="flex flex-col gap-2">
          {show.acts
            .slice()
            .sort((a, b) => a.position - b.position)
            .map(act => (
              <li key={act.band.id}>
                <BandLink
                  bandId={act.band.id}
                  className={`${act.position === 0 ? 'font-bold' : 'font-normal'} hover:underline text-ink`}
                >
                  <span data-testid="act-name">{act.band.name}</span>
                </BandLink>
                {act.note && <span className="text-ink-muted"> ({act.note})</span>}
              </li>
            ))}
        </ol>
      </section>

      <section>
        <h2 className="text-base font-semibold mb-3 text-ink">Venue</h2>
        <div className="flex flex-col gap-1 text-sm text-ink-soft">
          <span className="flex items-center gap-1.5">
            <BuildingOffice2Icon className="size-4 shrink-0 text-ink-faint" />
            <VenueLink venueId={show.venue.id} className="font-medium text-ink hover:underline">{show.venue.name}</VenueLink>
          </span>
          {show.venue.address && (
            <a
              href={mapsHref(show.venue)}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-1.5 w-fit hover:underline"
            >
              <MapPinIcon className="size-4 mt-0.5 shrink-0 text-ink-faint" />
              {show.venue.address}
            </a>
          )}
          {show.venue.websiteUrl && (
            <ExternalLink
              href={show.venue.websiteUrl}
              icon={GlobeAltIcon}
              className="w-fit text-link hover:underline"
            >
              Venue website
            </ExternalLink>
          )}
          {show.venue.description && (
            <p className="mt-2 text-ink-muted italic">{show.venue.description}</p>
          )}
        </div>
      </section>

      {show.notes && (
        <section>
          <h2 className="text-base font-semibold mb-1 text-ink">Notes</h2>
          <p className="text-sm text-ink-soft">{show.notes}</p>
        </section>
      )}
    </article>
  )
}
