'use client'

import { useEffect } from 'react'
import { installLinkBehaviour } from '@/lib/keepFilters'

/** Loads lib/keepFilters on every page (Next's way of running a page script; Astro will use a <script>). */
export default function LinkBehaviour() {
  useEffect(() => installLinkBehaviour(), [])
  return null
}
