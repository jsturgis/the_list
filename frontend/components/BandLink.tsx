'use client'

import Link from 'next/link'
import { useContext, type ReactNode } from 'react'
import { InBandModalContext, useBandModal } from './BandModalProvider'

interface BandLinkProps {
  bandId: number
  className?: string
  children: ReactNode
}

/**
 * A link to a Band page. A plain click opens the Band modal (replacing the history entry when
 * already inside it); modifier and middle clicks, or a missing provider, keep normal link behaviour.
 */
export default function BandLink({ bandId, className, children }: BandLinkProps) {
  const modal = useBandModal()
  const inModal = useContext(InBandModalContext)
  return (
    <Link
      href={`/bands/${bandId}`}
      className={className}
      onClick={e => {
        if (!modal || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
        e.preventDefault()
        modal.open(bandId, { replace: inModal })
      }}
    >
      {children}
    </Link>
  )
}
