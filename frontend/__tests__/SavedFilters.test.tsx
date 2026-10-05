import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import FilterBar from '@/components/FilterBar'
import { replaceQuery } from '@/lib/navigation'
import { fakeSupabase } from './fakeSupabase'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof import('./fakeSupabase').fakeSupabase> | null }))
vi.mock('@/lib/supabase', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/supabase')>()),
  get supabase() { return fake.current?.client ?? null },
  alertsAvailable: () => fake.current !== null,  // the build has the Supabase settings when there's a client
}))

const props = { showCount: 10, dbTotal: 100, genres: ['punk'], regions: ['east_bay'], ages: [], availableDates: [] }

beforeEach(() => {
  fake.current = fakeSupabase()
})

describe('Save control', () => {
  it('is unavailable until a filter is set', async () => {
    render(<FilterBar {...props} />)
    expect(await screen.findByRole('button', { name: /setup alert/i })).toBeDisabled()
  })

  it('suggests a name made from the filters', async () => {
    replaceQuery('genre=punk&region=east_bay')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))
    expect(screen.getByLabelText('Name')).toHaveValue('punk · East Bay')
  })

  it('names every kind of filter in the suggestion', async () => {
    replaceQuery('q=chapel&genre=punk&region=sf&free=1&age=21%2B&priceMax=20&fromDate=2026-10-03&toDate=2026-10-10')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))
    expect(screen.getByLabelText('Name')).toHaveValue('"chapel" · punk · SF · Free · 21+ · Up to $20 · Sat, Oct 3 – Sat, Oct 10')
  })

  it('asks a signed-out visitor for their email and sends a sign-in link that saves the search', async () => {
    replaceQuery('genre=punk&region=east_bay&utm_source=x')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'East Bay punk' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'fan@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: /email me a sign-in link/i }))

    // The form closes and a toast confirms.
    expect(await screen.findByRole('status')).toHaveTextContent(/check your email for a sign-in link/i)
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
    const [{ email, options }] = fake.current!.client.auth.signInWithOtp.mock.calls[0]
    expect(email).toBe('fan@example.com')
    const redirect = new URL(options!.emailRedirectTo!)
    expect(redirect.pathname).toBe('/alerts/')
    expect(redirect.searchParams.get('save')).toBe('genre=punk&region=east_bay')
    expect(redirect.searchParams.get('name')).toBe('East Bay punk')
    expect(fake.current!.client.insert).not.toHaveBeenCalled()
  })

  it('saves straight away for a signed-in visitor', async () => {
    fake.current!.state.email = 'fan@example.com'
    replaceQuery('genre=punk&region=east_bay')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))

    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'East Bay punk' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    const toast = await screen.findByRole('status')
    expect(toast).toHaveTextContent(/alert set up/i)
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
    expect(fake.current!.state.savedFilters).toMatchObject([{ name: 'East Bay punk', query: 'genre=punk&region=east_bay' }])
    expect(within(toast).getByRole('link', { name: /alerts/i })).toHaveAttribute('href', expect.stringMatching(/^\/alerts\/?$/))
  })

  it('shows why a save failed', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.insertError = { message: 'You can save up to 20 filters. Delete one to save another.' }
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Punk' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('You can save up to 20 filters')
  })
})

describe('Setup Alert limit', () => {
  const savedFilters = (n: number) =>
    Array.from({ length: n }, (_, i) => ({ id: `f${i}`, name: `Alert ${i}`, query: `genre=metal-${i}`, created_at: '2026-10-01T00:00:00Z' }))

  it('shows how many alerts a signed-in visitor has used', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = savedFilters(2)
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))
    expect(await screen.findByText('2 of 20 alerts used')).toBeInTheDocument()
  })

  it('explains the limit instead of offering to save at 20', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = savedFilters(20)
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))

    expect(await screen.findByText(/you have 20 alerts, the most allowed/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
    expect(screen.getByRole('link', { name: /delete one/i })).toHaveAttribute('href', expect.stringMatching(/^\/alerts\/?$/))
  })
})

describe('Setup Alert duplicates', () => {
  const saved = (name: string, query: string) => ({ id: name, name, query, created_at: '2026-10-01T00:00:00Z' })

  it('won\'t set up an alert the visitor already has, whatever order the filters are in', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = [saved('East Bay punk', 'genre=punk&region=east_bay')]
    replaceQuery('region=east_bay&genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))

    expect(await screen.findByText(/you already have an alert for these filters/i)).toHaveTextContent('“East Bay punk”')
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
    expect(screen.getByRole('link', { name: /manage your alerts/i })).toHaveAttribute('href', expect.stringMatching(/^\/alerts\/?$/))
  })

  it('treats searches that differ only in letter case as the same', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = [saved('Chapel', 'q=The+Chapel')]
    replaceQuery('q=the%20chapel')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))
    expect(await screen.findByText(/you already have an alert for these filters/i)).toBeInTheDocument()
  })

  it('still offers to save different filters', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = [saved('East Bay punk', 'genre=punk&region=east_bay')]
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))
    expect(await screen.findByText('1 of 20 alerts used')).toBeInTheDocument()
    expect(screen.queryByText(/already have an alert/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^save$/i })).toBeEnabled()
  })
})

describe('Save control dismissing', () => {
  const openSaved = async () => {
    fake.current!.state.email = 'fan@example.com'
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Punk' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    return screen.findByRole('status')
  }

  it('closes the form with Escape or a click outside it', async () => {
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /setup alert/i }))
    fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'Escape' })
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /setup alert/i }))
    fireEvent.mouseDown(screen.getByText(/showing 10 of 100/i))
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
  })

  it('lets the toast be dismissed', async () => {
    await openSaved()
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('Save control without Supabase configured', () => {
  it('is not shown', async () => {
    fake.current = null
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    await waitFor(() => expect(screen.getByText(/showing 10 of 100/i)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /setup alert/i })).not.toBeInTheDocument()
  })
})
