import type { BandMember } from '@/lib/types'
import Section from './Section'

const list = 'flex flex-wrap gap-x-4 gap-y-1 text-sm'
// Keys include the position: Discogs' "(2)" suffixes are stripped, so two members can share a name.

/** A Band's members from Discogs (DESIGN.md, "Band members"): current members, then "Formerly" and past ones. */
export default function BandMembers({ members }: { members: BandMember[] }) {
  const current = members.filter(m => m.active)
  const past = members.filter(m => !m.active)
  if (members.length === 0) return null
  return (
    <Section title="Members">
      {current.length > 0 && (
        <ul aria-label="Current members" className={`${list} font-semibold text-ink`}>
          {current.map((m, i) => <li key={`${m.name}-${i}`}>{m.name}</li>)}
        </ul>
      )}
      {past.length > 0 && (
        <div className="flex flex-col gap-1">
          <p id="former-members" className="text-xs text-ink-muted">Formerly</p>
          <ul aria-labelledby="former-members" className={`${list} text-ink-soft`}>
            {past.map((m, i) => <li key={`${m.name}-${i}`}>{m.name}</li>)}
          </ul>
        </div>
      )}
    </Section>
  )
}
