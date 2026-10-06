import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CurrencyDollarIcon } from '@heroicons/react/20/solid'
import FactList from '@/components/FactList'
import PageHeader from '@/components/PageHeader'
import Section from '@/components/Section'

describe('PageHeader', () => {
  it('shows the title as the page heading, with the eyebrow, subtitle and chips around it', () => {
    render(<PageHeader eyebrow="Fri, Oct 9" title="Static Bloom" subtitle="at The Fillmore"><span>Local</span></PageHeader>)
    const header = screen.getByRole('banner')
    expect(within(header).getByRole('heading', { level: 1, name: 'Static Bloom' })).toBeInTheDocument()
    expect(header).toHaveTextContent(/^Fri, Oct 9Static Bloomat The FillmoreLocal$/)
  })

  it('leaves out what it isn\'t given', () => {
    render(<PageHeader title="Your alerts" />)
    expect(screen.getByRole('banner')).toHaveTextContent(/^Your alerts$/)
  })
})

describe('Section', () => {
  it('is a region named by its h2', () => {
    render(<Section title="Similar Bands"><p>Moss Choir</p></Section>)
    const region = screen.getByRole('region', { name: 'Similar Bands' })
    expect(within(region).getByRole('heading', { level: 2, name: 'Similar Bands' })).toBeInTheDocument()
    expect(region).toHaveTextContent('Moss Choir')
  })

  it('takes a heading id, and passes data attributes to the section', () => {
    render(<Section title="Upcoming Shows" headingId="venue-upcoming-shows" plain data-upcoming-shows-list=""><p>…</p></Section>)
    const region = screen.getByRole('region', { name: 'Upcoming Shows' })
    expect(region).toHaveAttribute('aria-labelledby', 'venue-upcoming-shows')
    expect(region).toHaveAttribute('data-upcoming-shows-list')
  })

  it('puts an aside on the heading\'s line, outside the panel', () => {
    render(<Section title="Your alerts" aside="3 of 20 alerts"><p>East Bay punk</p></Section>)
    const subtitle = screen.getByText('3 of 20 alerts')
    expect(subtitle.previousElementSibling).toHaveTextContent('Your alerts')
    expect(subtitle.parentElement).not.toHaveTextContent('East Bay punk')
  })

  it('gives sections with different titles different heading ids', () => {
    render(<><Section title="Lineup"><p /></Section><Section title="Venue"><p /></Section></>)
    expect(screen.getByRole('region', { name: 'Lineup' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Venue' })).toBeInTheDocument()
  })
})

describe('FactList', () => {
  it('pairs each label with its value', () => {
    render(<FactList facts={[{ icon: CurrencyDollarIcon, label: 'Price', value: '$15' }, { icon: CurrencyDollarIcon, label: 'Ages', value: '21+' }]} />)
    const terms = screen.getAllByRole('term').map(t => t.textContent)
    const values = screen.getAllByRole('definition').map(d => d.textContent)
    expect(terms).toEqual(['Price', 'Ages'])
    expect(values).toEqual(['$15', '21+'])
  })
})
