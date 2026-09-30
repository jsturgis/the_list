'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Suspense, type ReactNode } from 'react'

interface VenueLinkProps {
  venueId: number
  className?: string
  children: ReactNode
}

function LinkWithFilters({ venueId, className, children }: VenueLinkProps) {
  const qs = useSearchParams().toString()
  return <Link href={qs ? `/venues/${venueId}?${qs}` : `/venues/${venueId}`} className={className}>{children}</Link>
}

/** Link to a Venue page that keeps the current filters, read in the browser (pages are static). */
export default function VenueLink(props: VenueLinkProps) {
  return (
    <Suspense fallback={<Link href={`/venues/${props.venueId}`} className={props.className}>{props.children}</Link>}>
      <LinkWithFilters {...props} />
    </Suspense>
  )
}
