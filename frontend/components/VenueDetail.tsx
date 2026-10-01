import type { ComponentType, SVGProps } from 'react'
import {
  BanknotesIcon, BookOpenIcon, BuildingOffice2Icon, CameraIcon, GlobeAltIcon, IdentificationIcon, MapIcon, MapPinIcon, PhoneIcon, StarIcon, UserIcon,
} from '@heroicons/react/20/solid'
import type { Show, Venue } from '@/lib/types'
import ExternalLink from './ExternalLink'
import VenueShowRows from './VenueShowRows'
import { mapsHref, telHref } from '@/lib/format'

const REGION_LABELS: Record<string, string> = {
  sf: 'SF',
  east_bay: 'East Bay',
  north_bay: 'North Bay',
  south_bay: 'South Bay',
  santa_cruz: 'Santa Cruz',
}

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
}

export default function VenueDetail({ venue, upcomingShows }: VenueDetailProps) {
  const rules: Rule[] = []
  if (venue.isSoberSpace) rules.push({ label: 'Sober space' })
  if (venue.isCashOnly) rules.push({ label: 'Cash only', icon: BanknotesIcon })
  if (venue.membershipRequired) rules.push({ label: 'Membership required', icon: IdentificationIcon })
  const agePolicy = venue.defaultAgeRestriction
    ? AGE_POLICY[venue.defaultAgeRestriction] ?? venue.defaultAgeRestriction
    : null

  return (
    <article className="max-w-2xl mx-auto flex flex-col gap-6">
      {venue.imageUrl && (
        // Hosts vary (and the site is a static export), so a plain <img> rather than next/image.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={venue.imageUrl} alt={venue.name} className="w-full max-h-72 object-cover rounded-lg" />
      )}
      <header>
        <h1 className="flex items-center gap-2 text-3xl font-bold text-zinc-900 dark:text-zinc-50">
          <BuildingOffice2Icon className="size-7 shrink-0 text-zinc-400 dark:text-zinc-500" />
          {venue.name}
        </h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
          {venue.neighborhood ? `${venue.neighborhood} · ` : ''}
          {venue.city}
          {venue.region && REGION_LABELS[venue.region] ? ` · ${REGION_LABELS[venue.region]}` : ''}
        </p>
        {rules.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {rules.map(({ label, icon: Icon }) => (
              <span key={label} className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                {Icon && <Icon className="size-3.5 shrink-0" />}
                {label}
              </span>
            ))}
          </div>
        )}
      </header>

      {(venue.nearestTransit || venue.instagram || agePolicy) && (
        <section className="flex flex-col gap-1 text-sm text-zinc-600 dark:text-zinc-300">
          {agePolicy && <p className="flex items-center gap-1.5"><UserIcon className="size-4 shrink-0 text-zinc-400 dark:text-zinc-500" />Usual ages: {agePolicy}</p>}
          {venue.nearestTransit && (
            <p className="flex items-start gap-1.5"><MapIcon className="size-4 mt-0.5 shrink-0 text-zinc-400 dark:text-zinc-500" />Transit: {venue.nearestTransit}</p>
          )}
          {venue.instagram && (
            <a href={instagramUrl(venue.instagram)} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 w-fit hover:underline">
              <CameraIcon className="size-4 shrink-0 text-zinc-400 dark:text-zinc-500" />
              {venue.instagram}
            </a>
          )}
        </section>
      )}

      {(venue.websiteUrl || venue.wikipediaUrl || venue.phone || venue.googleRating || venue.address) && (
        <section className="flex flex-col gap-2 text-sm text-zinc-600 dark:text-zinc-300">
          {venue.address && (
            <a
              href={mapsHref(venue)}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-1.5 w-fit hover:underline"
            >
              <MapPinIcon className="size-4 mt-0.5 shrink-0 text-zinc-400 dark:text-zinc-500" />
              {venue.address}
            </a>
          )}
          {venue.phone && (
            <a href={telHref(venue.phone)} className="flex items-center gap-1.5 w-fit hover:underline">
              <PhoneIcon className="size-4 shrink-0 text-zinc-400 dark:text-zinc-500" />
              {venue.phone}
            </a>
          )}
          {venue.googleRating && (
            <p className="flex items-center gap-1.5">
              <StarIcon className="size-4 shrink-0 text-amber-500 dark:text-amber-400" />
              Google rating: {venue.googleRating.toFixed(1)}
            </p>
          )}
          <div className="flex flex-wrap gap-3 mt-1">
            {venue.websiteUrl && (
              <ExternalLink
                href={venue.websiteUrl}
                icon={GlobeAltIcon}
                className="text-sm px-3 py-1.5 rounded bg-zinc-800 text-white hover:bg-zinc-700 dark:bg-zinc-700 dark:hover:bg-zinc-600"
              >
                Website
              </ExternalLink>
            )}
            {venue.wikipediaUrl && (
              <ExternalLink
                href={venue.wikipediaUrl}
                icon={BookOpenIcon}
                className="text-sm px-3 py-1.5 rounded bg-zinc-100 text-zinc-800 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              >
                Wikipedia
              </ExternalLink>
            )}
          </div>
        </section>
      )}

      {venue.description && (
        <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">
          {venue.description}
        </p>
      )}

      <VenueShowRows shows={upcomingShows} />
    </article>
  )
}
