import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import FilterBar from '@/components/FilterBar'
import { fakeSupabase } from './fakeSupabase'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof import('./fakeSupabase').fakeSupabase> | null }))
vi.mock('@/lib/supabase', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/supabase')>()),
  get supabase() { return fake.current?.client ?? null },
}))

let params = new URLSearchParams()
vi.mock('next/navigation', () => ({
  useSearchParams: () => params,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/',
}))

const props = { showCount: 10, dbTotal: 100, genres: ['punk'], regions: ['east_bay'], ages: [], availableDates: [] }

beforeEach(() => {
  fake.current = fakeSupabase()
  params = new URLSearchParams()
})

describe('Save control', () => {
  it('is unavailable until a filter is set', async () => {
    render(<FilterBar {...props} />)
    expect(await screen.findByRole('button', { name: /save search/i })).toBeDisabled()
  })

  it('asks a signed-out visitor for their email and sends a sign-in link that saves the search', async () => {
    params = new URLSearchParams('genre=punk&region=east_bay&utm_source=x')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))

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
    params = new URLSearchParams('genre=punk&region=east_bay')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))

    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'East Bay punk' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    const toast = await screen.findByRole('status')
    expect(toast).toHaveTextContent(/saved/i)
    expect(screen.queryByLabelText('Name')).not.toBeInTheDocument()
    expect(fake.current!.state.savedFilters).toMatchObject([{ name: 'East Bay punk', query: 'genre=punk&region=east_bay' }])
    expect(within(toast).getByRole('link', { name: /alerts/i })).toHaveAttribute('href', expect.stringMatching(/^\/alerts\/?$/))
  })

  it('shows why a save failed', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.insertError = { message: 'You can save up to 20 filters. Delete one to save another.' }
    params = new URLSearchParams('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Punk' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('You can save up to 20 filters')
  })
})

describe('Save control dismissing', () => {
  const openSaved = async () => {
    fake.current!.state.email = 'fan@example.com'
    params = new URLSearchParams('genre=punk')
    render(<FilterBar {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: /save search/i }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Punk' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    return screen.findByRole('status')
  }

  it('closes the form with Escape or a click outside it', async () => {
    params = new URLSearchParams('genre=punk')
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
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('Save control without Supabase configured', () => {
  it('is not shown', async () => {
    fake.current = null
    params = new URLSearchParams('genre=punk')
    render(<FilterBar {...props} />)
    await waitFor(() => expect(screen.getByText(/showing 10 of 100/i)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /save search/i })).not.toBeInTheDocument()
  })
})
