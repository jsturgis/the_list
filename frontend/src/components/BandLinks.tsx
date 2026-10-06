import type { BandLink } from '@/lib/types'
import ExternalLink from './ExternalLink'
import Section from './Section'

const GROUPS: [BandLink['group'], string][] = [['follow', 'Follow'], ['tour', 'Tour dates'], ['about', 'More about']]

/** A Band's follow, tour-date and reference links (DESIGN.md, "Band links"), one labelled line per group. */
export default function BandLinks({ links }: { links: BandLink[] }) {
  const groups = GROUPS.map(([group, label]) => [label, links.filter(l => l.group === group)] as const)
    .filter(([, inGroup]) => inGroup.length > 0)
  if (groups.length === 0) return null
  return (
    <Section title="Links">
      <dl className="flex flex-col gap-3 text-sm">
        {groups.map(([label, inGroup]) => (
          <div key={label} className="flex flex-col gap-1 sm:flex-row sm:gap-4">
            <dt className="w-28 shrink-0 text-ink-muted">{label}</dt>
            <dd>
              <ul className="flex flex-wrap gap-x-4 gap-y-1">
                {inGroup.map(link => (
                  <li key={link.service}>
                    <ExternalLink href={link.url} className="font-semibold text-ink hover:underline">
                      {link.label}
                    </ExternalLink>
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        ))}
      </dl>
    </Section>
  )
}
