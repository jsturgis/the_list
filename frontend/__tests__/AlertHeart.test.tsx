import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AlertHeart from '@/components/AlertHeart'
import { fakeSupabase } from './fakeSupabase'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof import('./fakeSupabase').fakeSupabase> | null }))
vi.mock('@/lib/supabase', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/supabase')>()),
  get supabase() { return fake.current?.client ?? null },
  alertsAvailable: () => fake.current !== null,
}))

const savedFilter = (name: string, query: string) => ({ id: name, name, query, created_at: '2026-10-01T00:00:00Z' })
const heart = () => screen.findByRole('button', { name: 'Get alerts for Neon Harbor' })

beforeEach(() => {
  fake.current = fakeSupabase()
})

describe('Alert heart, signed in', () => {
  beforeEach(() => { fake.current!.state.email = 'fan@example.com' })

  it('saves an alert for the Band, named after it', async () => {
    render(<AlertHeart kind="band" id={3} name="Neon Harbor" />)
    await waitFor(async () => expect(await heart()).toBeEnabled())
    expect(await heart()).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(await heart())
    await waitFor(async () => expect(await heart()).toHaveAttribute('aria-pressed', 'true'))
    expect(fake.current!.client.insert).toHaveBeenCalledWith({ name: 'Neon Harbor', query: 'bandId=3' })
    expect(screen.getByText("You'll get Neon Harbor's upcoming shows in your weekly email")).toBeInTheDocument()
  })

  it('shows an existing alert as on, and deletes it when pressed', async () => {
    fake.current!.state.savedFilters = [savedFilter('Neon Harbor', 'bandId=3'), savedFilter('Free', 'free=1')]
    render(<AlertHeart kind="band" id={3} name="Neon Harbor" />)
    await waitFor(async () => expect(await heart()).toHaveAttribute('aria-pressed', 'true'))
    fireEvent.click(await heart())
    await waitFor(async () => expect(await heart()).toHaveAttribute('aria-pressed', 'false'))
    expect(fake.current!.state.savedFilters.map(f => f.query)).toEqual(['free=1'])
    expect(screen.getByText('Stopped alerts for Neon Harbor')).toBeInTheDocument()
  })

  it('saves a Venue alert by the Venue\'s id', async () => {
    render(<AlertHeart kind="venue" id={2} name="924 Gilman Street" />)
    const venueHeart = await screen.findByRole('button', { name: 'Get alerts for 924 Gilman Street' })
    await waitFor(() => expect(venueHeart).toBeEnabled())
    fireEvent.click(venueHeart)
    await waitFor(() => expect(fake.current!.client.insert).toHaveBeenCalledWith({ name: '924 Gilman Street', query: 'venueId=2' }))
  })

  it('says so at the 20-alert limit, without saving', async () => {
    fake.current!.state.savedFilters = Array.from({ length: 20 }, (_, i) => savedFilter(`Alert ${i}`, `genre=g${i}`))
    render(<AlertHeart kind="band" id={3} name="Neon Harbor" />)
    await waitFor(async () => expect(await heart()).toBeEnabled())
    fireEvent.click(await heart())
    expect(await screen.findByText(/You have 20 alerts, the most allowed/)).toBeInTheDocument()
    expect(fake.current!.client.insert).not.toHaveBeenCalled()
  })
})

describe('Alert heart, signed out', () => {
  it('opens a panel that emails a sign-in link, which saves the alert', async () => {
    render(<AlertHeart kind="band" id={3} name="Neon Harbor" />)
    await waitFor(async () => expect(await heart()).toBeEnabled())
    expect(await heart()).not.toHaveAttribute('aria-pressed')
    fireEvent.click(await heart())
    expect(await heart()).toHaveAttribute('aria-expanded', 'true')
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'fan@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: /email me a sign-in link/i }))

    expect(await screen.findByText('Check your email for a sign-in link')).toBeInTheDocument()
    const [{ email, options }] = fake.current!.client.auth.signInWithOtp.mock.calls[0]
    expect(email).toBe('fan@example.com')
    const redirect = new URL(options!.emailRedirectTo!)
    expect(redirect.searchParams.get('save')).toBe('bandId=3')
    expect(redirect.searchParams.get('name')).toBe('Neon Harbor')
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
  })

  it('isn\'t shown on a build without alerts', () => {
    fake.current = null
    const { container } = render(<AlertHeart kind="band" id={3} name="Neon Harbor" />)
    expect(container).toBeEmptyDOMElement()
  })
})
