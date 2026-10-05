import type { Show } from '@/lib/types'
import { formatTime, formatPrice, formatDateLongYear, mapsHref } from '@/lib/format'
import { ArrowDownTrayIcon, CalendarDaysIcon, ClockIcon, GlobeAltIcon, MapPinIcon, SparklesIcon, TicketIcon, UserIcon } from '@heroicons/react/20/solid'
import { googleCalendarUrl, icsFilename, icsHref } from '@/lib/calendar'
import ActionLinks, { ActionLink } from './ActionLinks'
import BandLink from './BandLink'
import ExternalLink from './ExternalLink'
import FactList from './FactList'
import PageHeader from './PageHeader'
import Section from './Section'
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
  const acts = show.acts.slice().sort((a, b) => a.position - b.position)
  const upcoming = show.status === 'upcoming'

  return (
    <article className="flex flex-col gap-6">
      {show.specialEvent && (
        <div
          role="note"
          aria-label="Special event"
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-accent-soft-line bg-accent-soft text-accent-soft-ink"
        >
          <SparklesIcon className="size-5 shrink-0 text-link" />
          <span className="font-semibold">{show.specialEvent}</span>
        </div>
      )}

      <PageHeader
        eyebrow={
          <>
            <StatusBadge status={show.status} size="detail" />
            <span>{formatDateLongYear(show.date)}</span>
            {upcoming && (
              <span className="flex items-center">
                <a href={icsHref(show.id)} download={icsFilename(show)} aria-label="Add to calendar (.ics)" title="Add to calendar (.ics)"
                   className="rounded-full p-1 hover:bg-muted hover:text-link">
                  <ArrowDownTrayIcon className="size-4" />
                </a>
                <a href={googleCalendarUrl(show)} target="_blank" rel="noopener noreferrer" aria-label="Add to Google Calendar"
                   title="Add to Google Calendar" className="rounded-full p-1 hover:bg-muted hover:text-link">
                  <CalendarDaysIcon className="size-4" />
                </a>
              </span>
            )}
          </>
        }
        title={acts[0]?.band.name ?? 'Unknown'}
        subtitle={<>at <VenueLink venueId={show.venue.id} className="text-link underline underline-offset-2">{show.venue.name}</VenueLink> · {show.venue.city}</>}
      />

      <div className="flex flex-col gap-4 rounded-lg bg-surface p-5">
        <FactList facts={[
          ...(door ? [{ icon: ClockIcon, label: set ? 'Doors / Set' : 'Doors', value: set ? `${door} / ${set}` : door }] : []),
          { icon: TicketIcon, label: 'Price', value: price },
          { icon: UserIcon, label: 'Ages', value: age },
        ]} />
        <Flags show={show} size="detail" showBenefitCause />
      </div>

      {(show.ticketUrl || show.ticketProvider) && (
        <ActionLinks>
          {show.ticketUrl ? (
            <ActionLink href={show.ticketUrl} kind="primary" icon={TicketIcon} external>{ticketsLabel}</ActionLink>
          ) : show.ticketProvider ? (
            <span className="inline-flex items-center gap-1.5 px-1 py-2 text-sm text-ink-soft">
              <TicketIcon aria-hidden="true" className="size-4 shrink-0 text-ink-faint" />
              {ticketsLabel}
            </span>
          ) : null}
        </ActionLinks>
      )}

      <Section title="Lineup">
        <ol className="flex flex-col gap-2">
          {acts.map(act => (
            <li key={act.band.id} className={act.position === 0 ? 'text-xl' : 'text-base'}>
              <BandLink
                bandId={act.band.id}
                className={`${act.position === 0 ? 'font-bold' : 'font-normal'} hover:underline text-ink`}
              >
                <span data-testid="act-name">{act.band.name}</span>
              </BandLink>
              {act.note && <span className="text-base text-ink-muted"> ({act.note})</span>}
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Venue">
        <div className="flex flex-col gap-1.5 text-sm text-ink-soft">
          <VenueLink venueId={show.venue.id} className="w-fit text-base font-semibold text-ink hover:underline">{show.venue.name}</VenueLink>
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
              className="w-fit text-link underline underline-offset-2"
            >
              Venue website
            </ExternalLink>
          )}
          {show.venue.description && (
            <p className="mt-2 text-ink-muted">{show.venue.description}</p>
          )}
        </div>
      </Section>

      {show.notes && (
        <Section title="Notes">
          <p className="text-sm text-ink-soft">{show.notes}</p>
        </Section>
      )}
    </article>
  )
}
