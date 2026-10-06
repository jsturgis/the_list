import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import UnsubscribePage from '@/components/UnsubscribePage'
import { fakeSupabase, gate } from './fakeSupabase'

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof import('./fakeSupabase').fakeSupabase> | null }))
vi.mock('@/lib/supabase', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/supabase')>()),
  get supabase() { return fake.current?.client ?? null },
}))

const open = (search: string) => {
  window.history.replaceState({}, '', `/alerts/unsubscribe/${search}`)
  return render(<UnsubscribePage />)
}

beforeEach(() => {
  fake.current = fakeSupabase()
  fake.current.state.subscription = { enabled: true }
})

describe('Unsubscribe page', () => {
  it('turns weekly Alerts off for the link\'s token, without signing in', async () => {
    open('?token=good-token')
    expect(await screen.findByRole('heading', { name: /you're unsubscribed/i })).toBeInTheDocument()
    expect(fake.current!.client.rpc).toHaveBeenCalledWith('unsubscribe', { token: 'good-token' })
    expect(fake.current!.state.subscription).toEqual({ enabled: false })
    expect(screen.getByText(/your alerts are kept/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /alerts page/i })).toHaveAttribute('href', expect.stringMatching(/^\/alerts\/?$/))
  })

  it('shows a ghost message while it unsubscribes', async () => {
    const [held, release] = gate()
    fake.current!.state.dataGate = held
    const { container } = open('?token=good-token')
    expect(screen.getByText('Unsubscribing…')).toBeInTheDocument()
    expect(container.querySelector('[data-ghost]')).not.toBeNull()
    release()
    expect(await screen.findByRole('heading', { name: /you're unsubscribed/i })).toBeInTheDocument()
    expect(container.querySelector('[data-ghost]')).toBeNull()
  })

  it('says so when the link isn\'t valid', async () => {
    open('?token=nope')
    expect(await screen.findByRole('heading', { name: /link isn't valid/i })).toBeInTheDocument()
    expect(fake.current!.state.subscription).toEqual({ enabled: true })
  })

  it('treats a link without a token as not valid, without calling Supabase', async () => {
    open('')
    expect(await screen.findByRole('heading', { name: /link isn't valid/i })).toBeInTheDocument()
    expect(fake.current!.client.rpc).not.toHaveBeenCalled()
  })

  it('explains when Alerts aren\'t available on this copy of the site', async () => {
    fake.current = null
    open('?token=good-token')
    expect(await screen.findByText(/aren't available on this copy/i)).toBeInTheDocument()
  })
})
