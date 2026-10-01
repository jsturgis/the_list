import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { GlobeAltIcon } from '@heroicons/react/20/solid'
import ExternalLink from '@/components/ExternalLink'

describe('ExternalLink', () => {
  it('opens in a new tab without giving the page access to this one', () => {
    render(<ExternalLink href="https://venue.example/">Website</ExternalLink>)
    const link = screen.getByRole('link', { name: 'Website' })
    expect(link).toHaveAttribute('href', 'https://venue.example/')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('shows a leading icon and an external-link icon, both hidden from assistive technology', () => {
    render(<ExternalLink href="https://venue.example/" icon={GlobeAltIcon}>Website</ExternalLink>)
    const icons = screen.getByRole('link', { name: 'Website' }).querySelectorAll('svg')
    expect(icons).toHaveLength(2)
    icons.forEach(icon => expect(icon).toHaveAttribute('aria-hidden', 'true'))
  })
})
