import type { BandLink } from '@/lib/types'
import ExternalLink from './ExternalLink'
import Section from './Section'

/**
 * A Band's website, then its social profiles, Instagram, YouTube and the like (DESIGN.md, "Band links"), as a
 * wrapping list.
 */
export default function SocialLinks({ links, websiteUrl }: { links: BandLink[]; websiteUrl?: string | null }) {
  const social = links.filter(l => l.group === 'follow')
  if (social.length === 0 && !websiteUrl) return null
  return (
    <Section title="Social">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {websiteUrl && (
          <li>
            <ExternalLink href={websiteUrl} className="font-semibold text-ink hover:underline">Website</ExternalLink>
          </li>
        )}
        {social.map(link => (
          <li key={link.service}>
            <ExternalLink href={link.url} className="font-semibold text-ink hover:underline">{link.label}</ExternalLink>
          </li>
        ))}
      </ul>
    </Section>
  )
}
