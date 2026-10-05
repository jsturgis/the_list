import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BandLink from '@/components/BandLink'

describe('BandLink', () => {
  it("links to the Band's page", () => {
    render(<BandLink bandId={10} className="font-bold">Neon Harbor</BandLink>)
    const link = screen.getByRole('link', { name: 'Neon Harbor' })
    expect(link).toHaveAttribute('href', '/bands/10')
    expect(link).toHaveClass('font-bold')
  })
})
