import type { APIRoute, GetStaticPaths } from 'astro'
import { icsText } from '@/lib/calendar'
import { siteData } from '@/lib/siteData.server'
import type { Show } from '@/lib/types'

// One .ics file per Upcoming Show, linked from Show rows and Show pages ("Add to calendar").
export const getStaticPaths = (() =>
  siteData().showIds()
    .map(id => siteData().show(Number(id))!)
    // Upcoming Shows from the export's day: the ones lists and Show pages can still link to.
    .filter(show => show.status === 'upcoming' && show.date >= siteData().exportDay)
    .map(show => ({ params: { id: String(show.id) }, props: { show } }))) satisfies GetStaticPaths

export const GET: APIRoute<{ show: Show }> = ({ props }) =>
  new Response(icsText(props.show), { headers: { 'Content-Type': 'text/calendar; charset=utf-8' } })
