import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Flags, StatusBadge } from '@/components/ShowBadges'
import { makeShow } from './fixtures'

describe('StatusBadge', () => {
  it.each([['cancelled', 'Cancelled'], ['postponed', 'Postponed']] as const)('labels a %s Show', (status, label) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('renders nothing for an upcoming Show', () => {
    const { container } = render(<StatusBadge status="upcoming" />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('Flags', () => {
  const all = makeShow({
    isSoldOut: true, isBenefit: true, benefitCause: 'canned food drive', isMatinee: true, willSellOut: true,
    isPit: true, isDrinkTickets: true, isNoReentry: true,
  })

  it('labels every flag that is set', () => {
    render(<Flags show={all} size="card" />)
    for (const label of ['Sold out', 'Benefit', 'Matinee', 'Will Sell Out', 'Pit Warning', 'Drink Tickets', 'No Re-entry']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('puts the benefit cause in a tooltip on cards and inline on the detail page', () => {
    const { unmount } = render(<Flags show={all} size="card" />)
    expect(screen.getByText('Benefit').closest('[title]')).toHaveAttribute('title', 'canned food drive')
    unmount()
    render(<Flags show={all} size="detail" showBenefitCause />)
    expect(screen.getByText('Benefit: canned food drive')).toBeInTheDocument()
  })

  it('renders nothing when no flag is set', () => {
    const { container } = render(<Flags show={makeShow()} size="card" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('hides its icons from assistive technology', () => {
    const { container } = render(<Flags show={all} size="card" />)
    const icons = container.querySelectorAll('svg')
    expect(icons.length).toBeGreaterThan(0)
    icons.forEach(icon => expect(icon).toHaveAttribute('aria-hidden', 'true'))
  })
})
