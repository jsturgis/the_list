import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AlertsPage from '@/components/AlertsPage'
import { fakeSupabase, gate } from './fakeSupabase'

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

describe('Alerts page, while loading', () => {
  const ghosts = (c: HTMLElement) => c.querySelectorAll('[data-ghost]').length

  it('shows a ghost section until it knows whether someone is signed in', async () => {
    const [held, release] = gate()
    fake.current!.state.sessionGate = held
    const { container } = render(<AlertsPage />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(ghosts(container)).toBe(1)
    release()
    expect(await screen.findByRole('button', { name: /email me a sign-in link/i })).toBeInTheDocument()
    expect(ghosts(container)).toBe(0)
  })

  it('shows ghost alerts and a ghost weekly email setting until they load', async () => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = [savedFilter('Free', 'free=1')]
    fake.current!.state.subscription = { enabled: true }
    const [held, release] = gate()
    fake.current!.state.dataGate = held
    const { container } = render(<AlertsPage />)
    expect(await screen.findByText('Loading your alerts…')).toBeInTheDocument()
    expect(screen.getByText('Loading your weekly email setting…')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Your alerts', level: 2 })).toBeInTheDocument()
    release()
    expect(await screen.findByRole('link', { name: 'Free' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /email me these alerts each week/i })).toBeChecked()
    expect(ghosts(container)).toBe(0)
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

  it('doesn\'t save the filter a sign-in link carried when the person already has it', async () => {
    fake.current!.state.savedFilters = [savedFilter('East Bay punk', 'genre=punk&region=east_bay')]
    window.history.replaceState({}, '', '/alerts/?save=region%3Deast_bay%26genre%3Dpunk&name=Again')
    render(<AlertsPage />)

    expect(await screen.findByRole('status')).toHaveTextContent(/already have an alert for these filters: “East Bay punk”/i)
    expect(fake.current!.client.insert).not.toHaveBeenCalled()
    expect(screen.getAllByRole('link', { name: 'East Bay punk' })).toHaveLength(1)
    expect(screen.queryByRole('link', { name: 'Again' })).not.toBeInTheDocument()
    expect(window.location.search).toBe('')
  })

  it('says so when there are no Saved Filters yet', async () => {
    render(<AlertsPage />)
    expect(await screen.findByText(/no alerts yet/i)).toBeInTheDocument()
  })
})

describe('Managing alerts', () => {
  beforeEach(() => {
    fake.current!.state.email = 'fan@example.com'
    fake.current!.state.savedFilters = [savedFilter('East Bay punk', 'genre=punk&region=east_bay'), savedFilter('Free', 'free=1')]
    fake.current!.state.subscription = { enabled: true }
  })

  it('shows how many of the 20 alerts are used', async () => {
    render(<AlertsPage />)
    expect(await screen.findByText('2 of 20 alerts')).toBeInTheDocument()
  })

  it("moves focus to the next alert after a delete, and to the empty message when none are left", async () => {
    render(<AlertsPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete East Bay punk' }))
    await waitFor(() => expect(screen.getByRole('link', { name: 'Free' })).toHaveFocus())

    fireEvent.click(screen.getByRole('button', { name: 'Delete Free' }))
    await waitFor(() => expect(screen.getByText(/No alerts yet/)).toHaveFocus())
  })

  it('deletes an alert', async () => {
    render(<AlertsPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete East Bay punk' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Deleted “East Bay punk”')
    expect(screen.queryByRole('link', { name: 'East Bay punk' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Free' })).toBeInTheDocument()
    expect(fake.current!.state.savedFilters.map(f => f.name)).toEqual(['Free'])
    expect(screen.getByText('1 of 20 alerts')).toBeInTheDocument()
  })

  it('turns the weekly email off and on without deleting alerts', async () => {
    render(<AlertsPage />)
    const toggle = await screen.findByRole('checkbox', { name: /email me these alerts each week/i })
    expect(toggle).toBeChecked()

    fireEvent.click(toggle)
    await waitFor(() => expect(fake.current!.state.subscription).toEqual({ enabled: false }))
    expect(toggle).not.toBeChecked()
    expect(screen.getByText(/weekly emails are off/i)).toBeInTheDocument()
    expect(fake.current!.state.savedFilters).toHaveLength(2)

    fireEvent.click(toggle)
    await waitFor(() => expect(fake.current!.state.subscription).toEqual({ enabled: true }))
  })

  it('shows the weekly email setting as it was saved', async () => {
    fake.current!.state.subscription = { enabled: false }
    render(<AlertsPage />)
    expect(await screen.findByRole('checkbox', { name: /email me these alerts each week/i })).not.toBeChecked()
  })

  it('has no weekly email setting before the first alert', async () => {
    fake.current!.state.savedFilters = []
    fake.current!.state.subscription = null
    render(<AlertsPage />)
    expect(await screen.findByText(/no alerts yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('signs out', async () => {
    render(<AlertsPage />)
    fireEvent.click(await screen.findByRole('button', { name: /sign out/i }))
    expect(await screen.findByLabelText('Email')).toBeInTheDocument()
    expect(fake.current!.client.auth.signOut).toHaveBeenCalled()
  })
})
