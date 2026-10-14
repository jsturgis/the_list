import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BandLink from '@/components/BandLink'

describe('BandLink', () => {
  it("links to the Band's page by its slug", () => {
    render(<BandLink slug="neon-harbor" className="font-bold">Neon Harbor</BandLink>)
    const link = screen.getByRole('link', { name: 'Neon Harbor' })
    expect(link).toHaveAttribute('href', '/bands/neon-harbor/')
    expect(link).toHaveClass('font-bold')
  })
})
