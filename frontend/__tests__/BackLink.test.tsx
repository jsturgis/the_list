import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BackLink from '@/components/BackLink'

describe('BackLink', () => {
  it('links to the Shows list, marked to keep the filters and go back in history', () => {
    render(<BackLink />)
    const link = screen.getByRole('link', { name: 'Back' })
    expect(link).toHaveAttribute('href', '/')
    expect(link).toHaveAttribute('data-keep-filters')
    expect(link).toHaveAttribute('data-back')
  })
})
