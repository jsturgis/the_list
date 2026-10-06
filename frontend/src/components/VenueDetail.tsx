import type { ComponentType, ReactNode, SVGProps } from 'react'
import {
  BanknotesIcon, BookOpenIcon, CameraIcon, GlobeAltIcon, IdentificationIcon, MapIcon, MapPinIcon, PhoneIcon, StarIcon, UserIcon,
} from '@heroicons/react/20/solid'
import type { Show, Venue } from '@/lib/types'
import ActionLinks, { ActionLink } from './ActionLinks'
import PageHeader from './PageHeader'
import Section from './Section'
import VenueShowRows from './VenueShowRows'
import { REGION_LABELS, mapsHref, telHref } from '@/lib/format'

const AGE_POLICY: Record<string, string> = { all_ages: 'All ages', varies: 'Varies by show' }

/** "@catalystclub" -> "https://www.instagram.com/catalystclub/" */
function instagramUrl(handle: string): string {
  return `https://www.instagram.com/${handle.replace(/^@/, '')}/`
}

interface Rule {
  label: string
  icon?: ComponentType<SVGProps<SVGSVGElement>>
}

interface VenueDetailProps {
  venue: Venue
  upcomingShows: Show[]
  /** The alert heart (an island the Venue page passes in), on the title's line. */
  heart?: ReactNode
}

export default function VenueDetail({ venue, upcomingShows, heart }: VenueDetailProps) {
  const rules: Rule[] = []
  if (venue.isSoberSpace) rules.push({ label: 'Sober space' })
  if (venue.isCashOnly) rules.push({ label: 'Cash only', icon: BanknotesIcon })
  if (venue.membershipRequired) rules.push({ label: 'Membership required', icon: IdentificationIcon })
  const agePolicy = venue.defaultAgeRestriction
    ? AGE_POLICY[venue.defaultAgeRestriction] ?? venue.defaultAgeRestriction
    : null
  // The Region only when it adds something (not "Santa Cruz · Santa Cruz").
  const region = venue.region && REGION_LABELS[venue.region] !== venue.city ? REGION_LABELS[venue.region] : undefined
  const hasDetails = venue.address || venue.phone || venue.nearestTransit || agePolicy || venue.googleRating ||
    venue.instagram || venue.websiteUrl || venue.wikipediaUrl
  const item = 'flex items-start gap-1.5 w-fit'
  const icon = 'size-4 mt-0.5 shrink-0 text-ink-faint'

  return (
    <article className="flex flex-col gap-6">
      {venue.imageUrl && (
        <img src={venue.imageUrl} alt={venue.name} className="w-full max-h-72 object-cover rounded-lg" />
      )}

      <PageHeader title={venue.name} aside={heart} subtitle={[venue.city, region].filter(Boolean).join(' · ')}>
        {rules.map(({ label, icon: Icon }) => (
          <span key={label} className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-muted text-ink-soft">
            {Icon && <Icon className="size-3.5 shrink-0" />}
            {label}
          </span>
        ))}
      </PageHeader>

      {hasDetails && (
        <Section title="Details">
          <div className="flex flex-col gap-2 text-sm text-ink-soft">
            {venue.address && (
              <a href={mapsHref(venue)} target="_blank" rel="noopener noreferrer" className={`${item} hover:underline`}>
                <MapPinIcon className={icon} />
                {venue.address}
              </a>
            )}
            {venue.phone && (
              <a href={telHref(venue.phone)} className={`${item} hover:underline`}>
                <PhoneIcon className={icon} />
                {venue.phone}
              </a>
            )}
            {venue.nearestTransit && <p className={item}><MapIcon className={icon} />Transit: {venue.nearestTransit}</p>}
            {agePolicy && <p className={item}><UserIcon className={icon} />Usual ages: {agePolicy}</p>}
            {venue.googleRating && (
              <p className={item}><StarIcon className="size-4 mt-0.5 shrink-0 text-link" />Google rating: {venue.googleRating.toFixed(1)}</p>
            )}
            {venue.instagram && (
              <a href={instagramUrl(venue.instagram)} target="_blank" rel="noopener noreferrer" className={`${item} hover:underline`}>
                <CameraIcon className={icon} />
                {venue.instagram}
              </a>
            )}
          </div>
          {(venue.websiteUrl || venue.wikipediaUrl) && (
            <ActionLinks>
              {venue.websiteUrl && (
                <ActionLink href={venue.websiteUrl} kind="custom" icon={GlobeAltIcon} external className="bg-strong text-on-inverse hover:bg-strong-hover">
                  Website
                </ActionLink>
              )}
              {venue.wikipediaUrl && <ActionLink href={venue.wikipediaUrl} icon={BookOpenIcon} external>Wikipedia</ActionLink>}
            </ActionLinks>
          )}
        </Section>
      )}

      {venue.description && (
        <Section title="About">
          <p className="text-base text-ink-soft leading-relaxed">{venue.description}</p>
        </Section>
      )}

      <VenueShowRows shows={upcomingShows} />
    </article>
  )
}
