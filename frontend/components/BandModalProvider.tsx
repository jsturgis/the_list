'use client'

import { usePathname } from 'next/navigation'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import BandDetail from './BandDetail'
import Modal from './Modal'
import { bandShows, loadSiteData, similarBands } from '@/lib/data'
import type { SiteData } from '@/lib/types'

interface BandModal {
  /** Open a Band in the modal; `replace` swaps the current history entry instead of adding one. */
  open(bandId: number, options?: { replace?: boolean }): void
}

const BandModalContext = createContext<BandModal | null>(null)
/** True inside the Band modal, so links there replace the history entry rather than pushing. */
export const InBandModalContext = createContext(false)

export function useBandModal(): BandModal | null {
  return useContext(BandModalContext)
}

/**
 * Client-side Band modal (static export can't use intercepting routes). Opening a Band pushes
 * /bands/<id> onto history (Next's router syncs with pushState without navigating), moving between
 * Bands inside the modal replaces that entry, closing goes back, and browser Back closes it.
 * Loading /bands/<id> directly renders the full static Band page instead.
 */
export default function BandModalProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [bandId, setBandId] = useState<number | null>(null)
  const [data, setData] = useState<SiteData | null>(null)

  const show = useCallback((id: number | null) => {
    setBandId(id)
    if (id !== null) loadSiteData().then(setData).catch(() => {})
  }, [])

  const open = useCallback<BandModal['open']>((id, { replace = false } = {}) => {
    const url = `/bands/${id}`
    if (replace) window.history.replaceState({ bandModal: id }, '', url)
    else window.history.pushState({ bandModal: id }, '', url)
    show(id)
  }, [show])

  // Back/Forward: the history entry says whether a Band modal belongs on top of the page.
  useEffect(() => {
    const onPopState = (e: PopStateEvent) => {
      const id = (e.state as { bandModal?: unknown } | null)?.bandModal
      show(typeof id === 'number' ? id : null)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [show])

  // Following a link out of the modal (e.g. to a Show page) closes it.
  const [prevPathname, setPrevPathname] = useState(pathname)
  if (pathname !== prevPathname) {
    setPrevPathname(pathname)
    if (bandId !== null && pathname !== `/bands/${bandId}`) setBandId(null)
  }

  const context = useMemo(() => ({ open }), [open])
  const band = bandId !== null ? data?.bands.get(bandId) : undefined

  return (
    <BandModalContext.Provider value={context}>
      {children}
      {bandId !== null && (
        <Modal onClose={() => window.history.back()}>
          <InBandModalContext.Provider value={true}>
            {band && data ? (
              <BandDetail band={band} upcomingShows={bandShows(data.shows, band.id)} similarBands={similarBands(band, data.bands)} />
            ) : (
              <p className="text-zinc-500 dark:text-zinc-400 py-8 text-center">{data ? 'Band not found.' : 'Loading…'}</p>
            )}
          </InBandModalContext.Provider>
        </Modal>
      )}
    </BandModalContext.Provider>
  )
}
