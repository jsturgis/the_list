import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AlertsPage from '@/components/AlertsPage'
import { fakeSupabase } from './fakeSupabase'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof import('./fakeSupabase').fakeSupabase> | null }))
vi.mock('@/lib/supabase', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/supabase')>()),
  get supabase() { return fake.current?.client ?? null },
}))

const savedFilter = (name: string, query: string) => ({ id: name, name, query, created_at: '2026-10-01T00:00:00Z' })

beforeEach(() => {
  fake.current = fakeSupabase()
  window.history.replaceState({}, '', '/alerts/')
})

describe('Alerts page, signed out', () => {
  it('offers a sign-in link by email', async () => {
    render(<AlertsPage />)
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'fan@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: /email me a sign-in link/i }))

    expect(await screen.findByRole('status')).toHaveTextContent(/check your email for a sign-in link/i)
    expect(screen.getByLabelText('Email')).toHaveValue('')
    const [{ email, options }] = fake.current!.client.auth.signInWithOtp.mock.calls[0]
    expect(email).toBe('fan@example.com')
    expect(new URL(options!.emailRedirectTo!).pathname).toBe('/alerts/')
    expect(new URL(options!.emailRedirectTo!).search).toBe('')
  })
})

describe('Alerts page, signed in', () => {
  beforeEach(() => { fake.current!.state.email = 'fan@example.com' })

  it('lists Saved Filters, each opening the Shows list with its filters', async () => {
    fake.current!.state.savedFilters = [savedFilter('East Bay punk', 'genre=punk&region=east_bay'), savedFilter('Free', 'free=1')]
    render(<AlertsPage />)

    expect(await screen.findByRole('link', { name: 'East Bay punk' })).toHaveAttribute('href', '/?genre=punk&region=east_bay')
    expect(screen.getByRole('link', { name: 'Free' })).toHaveAttribute('href', '/?free=1')
    expect(screen.getByText(/fan@example\.com/)).toBeInTheDocument()
  })

  it('saves the filter the sign-in link carried, once, and tidies the address bar', async () => {
    window.history.replaceState({}, '', '/alerts/?save=genre%3Dpunk&name=Punk')
    render(<AlertsPage />)

    expect(await screen.findByRole('link', { name: 'Punk' })).toHaveAttribute('href', '/?genre=punk')
    expect(fake.current!.client.insert).toHaveBeenCalledTimes(1)
    expect(fake.current!.state.savedFilters).toMatchObject([{ name: 'Punk', query: 'genre=punk' }])
    expect(window.location.search).toBe('')
  })

  it('says so when there are no Saved Filters yet', async () => {
    render(<AlertsPage />)
    expect(await screen.findByText(/no alerts yet/i)).toBeInTheDocument()
  })
})

describe('Header link to the Alerts page', () => {
  it('is shown when Alerts are available', async () => {
    const { default: AlertsLink } = await import('@/components/AlertsLink')
    render(<AlertsLink />)
    expect(await screen.findByRole('link', { name: 'Your alerts' })).toHaveAttribute('href', expect.stringMatching(/^\/alerts\/?$/))
  })

  it('is hidden when the build has no Supabase settings', async () => {
    fake.current = null
    const { default: AlertsLink } = await import('@/components/AlertsLink')
    const { container } = render(<AlertsLink />)
    expect(container).toBeEmptyDOMElement()
  })
})
