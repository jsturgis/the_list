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

/** The toast: the status region that isn't the filter bar's live Shows count. */
const isToast = (el: HTMLElement) => !/^(Showing|Loading) /.test(el.textContent ?? '')
const findToast = () => waitFor(() => {
  const toast = screen.getAllByRole('status').find(isToast)
  if (!toast) throw new Error('No toast')
  return toast
})

const props = { showCount: 10, dbTotal: 100, genres: ['punk'], regions: ['east_bay'], ages: [], availableDates: [] }

beforeEach(() => {
  fake.current = fakeSupabase()
})

describe('A list pinned to one Band or Venue', () => {
  it('shows the Band as a chip, which removes it', async () => {
    replaceQuery('bandId=3&region=sf')
    render(<FilterBar {...props} pinned={{ param: 'bandId', name: 'Neon Harbor' }} />)
    expect(screen.getByText('Shows with')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all shows, not only with Neon Harbor' }))
    await waitFor(() => expect(window.location.search).toBe('?region=sf'))
  })

  it('names a Save search after the Band', async () => {
    replaceQuery('bandId=3')
    render(<FilterBar {...props} pinned={{ param: 'bandId', name: 'Neon Harbor' }} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    expect(screen.getByLabelText('Name')).toHaveValue('Neon Harbor')
  })
})

describe('Save control', () => {
  it('is unavailable until a filter is set', async () => {
    render(<FilterBar {...props} />)
    expect(await screen.findByRole('button', { name: /save search/i })).toBeDisabled()
  })

  it('suggests a name made from the filters', async () => {
    replaceQuery('genre=punk&region=east_bay')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    expect(screen.getByLabelText('Name')).toHaveValue('punk · East Bay')
  })

  it('names every kind of filter in the suggestion', async () => {
    replaceQuery('q=chapel&genre=punk&region=sf&free=1&age=21%2B&priceMax=20&fromDate=2026-10-03&toDate=2026-10-10')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    expect(screen.getByLabelText('Name')).toHaveValue('"chapel" · punk · SF · Free · 21+ · Up to $20 · Sat, Oct 3 – Sat, Oct 10')
  })

  it('asks a signed-out visitor for their email and sends a sign-in link that saves the search', async () => {
    replaceQuery('genre=punk&region=east_bay&utm_source=x')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'East Bay punk' } })
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'fan@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: /email me a sign-in link/i }))

    // The form closes and a toast confirms.
    expect(await findToast()).toHaveTextContent(/check your email for a sign-in link/i)
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
    const [{ email, options }] = fake.current!.client.auth.signInWithOtp.mock.calls[0]
    expect(email).toBe('fan@example.com')
    const redirect = new URL(options!.emailRedirectTo!)
    expect(redirect.pathname).toBe('/alerts/')
    expect(redirect.searchParams.get('save')).toBe('genre=punk&region=east_bay')
    expect(redirect.searchParams.get('name')).toBe('East Bay punk')
    expect(fake.current!.client.insert).not.toHaveBeenCalled()
  })

  it('saves when Save is clicked in Safari, where focus jumps to <main> mid-click', async () => {
    fake.current!.state.email = 'fan@example.com'
    replaceQuery('genre=punk&region=east_bay')
    const { container } = render(<main tabIndex={-1}><FilterBar {...props} /></main>)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    await screen.findByText(/alerts used/)
    // Safari doesn't focus a clicked button: the name field loses focus to the nearest focusable ancestor first.
    fireEvent.focusOut(screen.getByLabelText('Name'), { relatedTarget: container.querySelector('main') })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await findToast()
    expect(fake.current!.state.savedFilters).toMatchObject([{ query: 'genre=punk&region=east_bay' }])
  })

  it('closes when focus moves on to something else', async () => {
    replaceQuery('genre=punk')
    render(<><FilterBar {...props} /><a href="/next">Next</a></>)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    fireEvent.focusOut(screen.getByLabelText('Name'), { relatedTarget: screen.getByRole('link', { name: 'Next' }) })
    await waitFor(() => expect(screen.queryByLabelText('Name')).not.toBeInTheDocument())
  })

  it('saves straight away for a signed-in visitor', async () => {
    fake.current!.state.email = 'fan@example.com'
    replaceQuery('genre=punk&region=east_bay')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))

    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'East Bay punk' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    const toast = await findToast()
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
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Punk' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('You can save up to 20 filters')
  })
})

describe('Save search limit', () => {
  const savedFilters = (n: number) =>
    Array.from({ length: n }, (_, i) => ({ id: `f${i}`, name: `Alert ${i}`, query: `genre=metal-${i}`, created_at: '2026-10-01T00:00:00Z' }))

  it('shows how many alerts a signed-in visitor has used', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = savedFilters(2)
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    expect(await screen.findByText('2 of 20 alerts used')).toBeInTheDocument()
  })

  it('explains the limit instead of offering to save at 20', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = savedFilters(20)
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))

    expect(await screen.findByText(/you have 20 alerts, the most allowed/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
    expect(screen.getByRole('link', { name: /delete one/i })).toHaveAttribute('href', expect.stringMatching(/^\/alerts\/?$/))
  })
})

describe('Save search duplicates', () => {
  const saved = (name: string, query: string) => ({ id: name, name, query, created_at: '2026-10-01T00:00:00Z' })

  it('won\'t set up an alert the visitor already has, whatever order the filters are in', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = [saved('East Bay punk', 'genre=punk&region=east_bay')]
    replaceQuery('region=east_bay&genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))

    expect(await screen.findByText(/you already have an alert for these filters/i)).toHaveTextContent('“East Bay punk”')
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
    expect(screen.getByRole('link', { name: /manage your alerts/i })).toHaveAttribute('href', expect.stringMatching(/^\/alerts\/?$/))
  })

  it('treats searches that differ only in letter case as the same', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = [saved('Chapel', 'q=The+Chapel')]
    replaceQuery('q=the%20chapel')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    expect(await screen.findByText(/you already have an alert for these filters/i)).toBeInTheDocument()
  })

  it('still offers to save different filters', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = [saved('East Bay punk', 'genre=punk&region=east_bay')]
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
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
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Punk' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    return findToast()
  }

  it('moves focus into the form, and back to the button on Escape', async () => {
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    const button = await screen.findByRole('button', { name: /save search/i })
    fireEvent.click(button)
    expect(screen.getByLabelText('Name')).toHaveFocus()
    fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'Escape' })
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
    expect(button).toHaveFocus()
  })

  it('closes when focus leaves the form, so it never stays open behind the keyboard', async () => {
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    const outside = screen.getByLabelText('Search')
    fireEvent.focusOut(screen.getByLabelText('Name'), { relatedTarget: outside })
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
  })

  it('keeps focus on the Save search button after saving, and after dismissing the toast', async () => {
    await openSaved()
    const button = screen.getByRole('button', { name: /save search/i })
    expect(button).toHaveFocus()
    screen.getByRole('button', { name: /dismiss/i }).focus()
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(button).toHaveFocus()
  })

  it('closes the form with Escape or a click outside it', async () => {
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'Escape' })
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /save search/i }))
    fireEvent.mouseDown(screen.getByText(/showing 10 of 100/i))
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
  })

  it('lets the toast be dismissed', async () => {
    await openSaved()
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(screen.queryAllByRole('status').filter(isToast)).toEqual([])
  })
})

describe('Save control without Supabase configured', () => {
  it('is not shown', async () => {
    fake.current = null
    replaceQuery('genre=punk')
    render(<FilterBar {...props} />)
    await waitFor(() => expect(screen.getByText(/showing 10 of 100/i)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /save search/i })).not.toBeInTheDocument()
  })
})
