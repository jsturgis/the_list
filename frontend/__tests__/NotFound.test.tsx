import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import NotFound from '@/app/not-found'

describe('NotFound', () => {
  it('says the page is missing and links home', () => {
    render(<NotFound />)
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /this week's shows/i })).toHaveAttribute('href', '/')
  })
})
