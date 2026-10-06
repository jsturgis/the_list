import type { BandLink } from '@/lib/types'
import ExternalLink from './ExternalLink'
import Section from './Section'

/** A Band's social profiles, Instagram, YouTube and the like (DESIGN.md, "Band links"), as a wrapping list. */
export default function SocialLinks({ links }: { links: BandLink[] }) {
  const social = links.filter(l => l.group === 'follow')
  if (social.length === 0) return null
  return (
    <Section title="Social">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {social.map(link => (
          <li key={link.service}>
            <ExternalLink href={link.url} className="font-semibold text-ink hover:underline">{link.label}</ExternalLink>
          </li>
        ))}
      </ul>
    </Section>
  )
}
