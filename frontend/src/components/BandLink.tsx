import type { ReactNode } from 'react'
import { href } from '@/lib/basePath'

interface BandLinkProps {
  /** The Band's slug. */
  slug: string
  className?: string
  children: ReactNode
}

/** A link to a Band's page. */
export default function BandLink({ slug, className, children }: BandLinkProps) {
  return (
    <a href={href(`/bands/${slug}/`)} className={className}>
      {children}
    </a>
  )
}
