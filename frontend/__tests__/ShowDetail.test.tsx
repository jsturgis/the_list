import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ShowDetail from '@/components/ShowDetail'
import { makeShow, makeVenue, makeBand } from './fixtures'

describe('ShowDetail', () => {
  const show = makeShow({
    id: 1,
    date: '2026-10-03',
    doorTime: '19:00:00',
    setTime: '20:00:00',
    venue: makeVenue({
      name: 'The Fillmore',
      address: '1805 Geary Blvd, San Francisco, CA 94115',
      city: 'San Francisco',
      region: 'sf',
      websiteUrl: 'https://www.thefillmore.com',
    }),
    acts: [
      { position: 0, band: makeBand({ id: 1, name: 'Headliner Act', genres: ['rock'] }) },
      { position: 1, band: makeBand({ id: 2, name: 'Support One', genres: ['indie'] }) },
      { position: 2, band: makeBand({ id: 3, name: 'Opener', genres: ['folk'] }) },
    ],
    priceMin: 25,
    priceMax: 30,
    isFree: false,
    ageRestriction: '21+',
    status: 'upcoming',
    isRecommended: false,
    willSellOut: false,
    isPit: false,
    isDrinkTickets: false,
    isNoReentry: false,
    notes: null,
  })

  it('renders all acts in order', () => {
    render(<ShowDetail show={show} />)
    const actNames = screen.getAllByTestId('act-name').map(el => el.textContent)
    expect(actNames).toEqual(['Headliner Act', 'Support One', 'Opener'])
  })

  it('marks the headliner in bold instead of with a label', () => {
    render(<ShowDetail show={show} />)
    expect(screen.queryByText(/^Headliner$/)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Headliner Act' })).toHaveClass('font-bold')
    expect(screen.getByRole('link', { name: 'Support One' })).not.toHaveClass('font-bold')
  })

  it('links each act to its band page', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByRole('link', { name: /Headliner Act/i })).toHaveAttribute('href', '/bands/1')
    expect(screen.getByRole('link', { name: /Support One/i })).toHaveAttribute('href', '/bands/2')
    expect(screen.getByRole('link', { name: /Opener/i })).toHaveAttribute('href', '/bands/3')
  })

  it('renders venue address', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByText(/1805 Geary Blvd/)).toBeInTheDocument()
  })

  it('renders venue website link', () => {
    render(<ShowDetail show={show} />)
    const link = screen.getByRole('link', { name: /venue website/i })
    expect(link).toHaveAttribute('href', 'https://www.thefillmore.com')
  })

  it('does not render venue website link when websiteUrl is null', () => {
    render(<ShowDetail show={makeShow({ venue: makeVenue({ websiteUrl: null }) })} />)
    expect(screen.queryByRole('link', { name: /venue website/i })).not.toBeInTheDocument()
  })

  it('renders Cancelled status prominently', () => {
    render(<ShowDetail show={makeShow({ status: 'cancelled' })} />)
    expect(screen.getByText(/cancelled/i)).toBeInTheDocument()
  })

  it('renders Postponed status prominently', () => {
    render(<ShowDetail show={makeShow({ status: 'postponed' })} />)
    expect(screen.getByText(/postponed/i)).toBeInTheDocument()
  })

  it('renders door time', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByText(/7:00/i)).toBeInTheDocument()
  })

  it('renders price', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByText(/\$25/)).toBeInTheDocument()
  })

  it('renders age restriction', () => {
    render(<ShowDetail show={show} />)
    expect(screen.getByText(/21\+/)).toBeInTheDocument()
  })

  it('renders all flag indicators when set', () => {
    render(
      <ShowDetail
        show={makeShow({
          isPit: true,
          willSellOut: true,
          isDrinkTickets: true,
          isNoReentry: true,
        })}
      />,
    )
    expect(screen.getByText(/pit/i)).toBeInTheDocument()
    expect(screen.getByText(/sell out/i)).toBeInTheDocument()
    expect(screen.getByText(/drink/i)).toBeInTheDocument()
    expect(screen.getByText(/re-entry/i)).toBeInTheDocument()
  })
})
