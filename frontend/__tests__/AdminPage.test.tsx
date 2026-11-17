import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AdminPage, { readLine } from '@/components/AdminPage'
import type { IngestJob } from '@/lib/ingestJobs'

/** A stand-in for the Supabase client: who's signed in, the ingest_jobs rows, and the Realtime channel. */
function fakeClient() {
  const state = {
    user: null as { id: string; email: string; app_metadata: Record<string, unknown> } | null,
    jobs: [] as IngestJob[],
    realtime: 'SUBSCRIBED',
    onChange: null as ((payload: { new: IngestJob }) => void) | null,
  }
  const client = {
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: state.user ? { user: state.user, access_token: 'token-1' } : null },
        error: null,
      })),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
      signInWithOtp: vi.fn<(args: { email: string; options?: { emailRedirectTo?: string } }) => Promise<{ error: null }>>(
        async () => ({ error: null }),
      ),
      signOut: vi.fn(async () => ({ error: null })),
    },
    from: vi.fn((table: string) => {
      if (table !== 'ingest_jobs') throw new Error(`unexpected table ${table}`)
      return { select: () => ({ order: () => ({ limit: async () => ({ data: [...state.jobs], error: null }) }) }) }
    }),
    channel: vi.fn(() => {
      const channel = {
        on: (_event: string, _filter: unknown, listener: (payload: { new: IngestJob }) => void) => {
          state.onChange = listener
          return channel
        },
        subscribe: (callback: (status: string) => void) => {
          callback(state.realtime)
          return channel
        },
      }
      return channel
    }),
    removeChannel: vi.fn(),
  }
  return { client, state }
}

const fake = vi.hoisted(() => ({ current: null as ReturnType<typeof fakeClient> | null }))
vi.mock('@/lib/supabase', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/supabase')>()),
  get supabase() {
    return fake.current?.client ?? null
  },
}))

const ADMIN = { id: 'user-1', email: 'admin@example.com', app_metadata: { permissions: ['admin'] } }
const URL_1 = 'https://www.ticketweb.com/event/wet-leg-the-chapel-tickets/123'

function job(changes: Partial<IngestJob> = {}): IngestJob {
  return {
    id: 'job-1',
    provider: 'ticketweb',
    url: URL_1,
    screenshot_path: null,
    status: 'queued',
    phase: 'queued',
    detail: null,
    message: null,
    extracted: null,
    show_id: null,
    workflow_run_url: null,
    attempts: 0,
    created_at: '2026-11-17T20:00:00Z',
    updated_at: '2026-11-17T20:00:00Z',
    ...changes,
  }
}

const fetchMock = vi.fn()

beforeEach(() => {
  fake.current = fakeClient()
  vi.stubEnv('PUBLIC_SUPABASE_URL', 'https://project.supabase.co')
  vi.stubEnv('PUBLIC_SUPABASE_ANON_KEY', 'sb_publishable_1')
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  window.history.replaceState({}, '', '/admin/')
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('Admin page, signed out', () => {
  it('offers a sign-in link that comes back to the Admin page', async () => {
    render(<AdminPage />)
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'admin@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: /email me a sign-in link/i }))

    await waitFor(() => expect(fake.current!.client.auth.signInWithOtp).toHaveBeenCalled())
    const [{ options }] = fake.current!.client.auth.signInWithOtp.mock.calls[0]
    expect(new URL(options!.emailRedirectTo!).pathname).toBe('/admin/')
  })
})

describe('Admin page, signed in but not an admin', () => {
  it('says so, and shows nothing else', async () => {
    fake.current!.state.user = { ...ADMIN, app_metadata: {} }
    render(<AdminPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/isn.t an admin/)
    expect(screen.queryByLabelText('Event links')).not.toBeInTheDocument()
    expect(fake.current!.client.from).not.toHaveBeenCalled()
  })
})

describe('Admin page, as an admin', () => {
  beforeEach(() => {
    fake.current!.state.user = ADMIN
  })

  it('checks each link as it is typed: any site, but only web pages', async () => {
    render(<AdminPage />)
    fireEvent.change(await screen.findByLabelText('Event links'), {
      target: { value: `${URL_1}\nhttps://www.bandsintown.com/e/1\nhttp://localhost:11434/api\n` },
    })

    const links = within(screen.getByRole('list', { name: 'Links' })).getAllByRole('listitem')
    expect(links).toHaveLength(3)
    expect(within(links[0]).getByLabelText('Ready')).toBeInTheDocument()
    expect(within(links[1]).getByLabelText('Ready')).toBeInTheDocument()
    expect(links[2]).toHaveTextContent(/isn.t a public website/)
  })

  it('takes screenshots dropped on the form, and lights the drop zone while they are dragged over it', async () => {
    render(<AdminPage />)
    const zone = (await screen.findByText(/drag screenshots here/i)).closest('#admin-drop-zone')!
    const shot = new File(['png'], 'dropped.png', { type: 'image/png' })
    const dataTransfer = { types: ['Files'], files: [shot], dropEffect: 'none' }

    fireEvent.dragOver(zone, { dataTransfer })
    expect(zone).toHaveAttribute('data-dragging')
    expect(screen.getByText('Drop to add')).toBeInTheDocument()
    fireEvent.drop(zone, { dataTransfer })

    expect(zone).not.toHaveAttribute('data-dragging')
    expect(screen.getByText('dropped.png')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add shows' })).toBeEnabled()
  })

  it('offers a screenshot instead when a link’s page could not be read', async () => {
    fake.current!.state.jobs = [
      job({ provider: 'page', url: 'https://www.bandsintown.com/e/1', status: 'failed', phase: 'fetching_page',
            message: "couldn't fetch https://www.bandsintown.com/e/1: 403. Take a screenshot of the event and add that instead." }),
      job({ id: 'job-2', status: 'failed', phase: 'fetching_page', message: 'The Chapel is in Portland, not a Bay Area city we know' }),
    ]
    Element.prototype.scrollIntoView = vi.fn()   // not in jsdom
    render(<AdminPage />)

    expect(await screen.findByText('bandsintown.com')).toBeInTheDocument()
    const offers = screen.getAllByRole('button', { name: 'Add a screenshot instead' })
    expect(offers).toHaveLength(1)   // not for the event that can't be added at all
    fireEvent.click(offers[0])
    expect(screen.getByRole('button', { name: 'Choose screenshots' })).toHaveFocus()
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
  })

  it('adds the valid links and screenshots as the signed-in admin, and lists the new jobs', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ jobs: [job()], rejected: [] }), { status: 200 }))
    render(<AdminPage />)
    expect(await screen.findByText(/no jobs yet/i)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Event links'), { target: { value: `${URL_1}\nnot a link` } })
    const shot = new File(['png'], 'event.png', { type: 'image/png' })
    fireEvent.change(screen.getByLabelText('Screenshots'), { target: { files: [shot] } })
    expect(screen.getByText('event.png')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add shows' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Added 1 job')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('https://project.supabase.co/functions/v1/admin/v1/shows')
    expect(init.headers.Authorization).toBe('Bearer token-1')
    const form = init.body as FormData
    expect(form.getAll('url')).toEqual([URL_1])
    expect((form.getAll('screenshot')[0] as File).name).toBe('event.png')
    // The job is listed; what wasn't sent stays in the box to fix.
    expect(screen.getByRole('link', { name: /wet leg the chapel/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Event links')).toHaveValue('not a link')
    expect(screen.queryByText('event.png')).not.toBeInTheDocument()
  })

  it('says what the server turned away', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ jobs: [], rejected: [{ input: 'huge.png', reason: 'is over 10 MB' }] }), { status: 200 }),
    )
    render(<AdminPage />)
    fireEvent.change(await screen.findByLabelText('Screenshots'), {
      target: { files: [new File(['png'], 'huge.png', { type: 'image/png' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add shows' }))

    expect(await screen.findByText('Not added:')).toBeInTheDocument()
    expect(screen.getByText('is over 10 MB')).toBeInTheDocument()
  })

  it('shows each job’s steps, the one it is on, and what it is doing', async () => {
    fake.current!.state.jobs = [
      job({ status: 'running', phase: 'bands', detail: 'Looking up Band 2 of 3: Wet Leg', workflow_run_url: 'https://github.com/run/1' }),
    ]
    render(<AdminPage />)

    const row = await screen.findByText('Looking up Band 2 of 3: Wet Leg')
    const steps = within(row.closest('li')!).getByRole('list', { name: 'Steps' })
    expect(within(steps).getByText('Bands').closest('li')).toHaveAttribute('aria-current', 'step')
    expect(within(steps).getAllByLabelText('done')).toHaveLength(4)   // Queued, Dispatched, Fetching, Venue
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Workflow run' })).toHaveAttribute('href', 'https://github.com/run/1')
  })

  it('follows a job as it changes', async () => {
    fake.current!.state.jobs = [job()]
    render(<AdminPage />)
    expect(await screen.findByText('Queued', { selector: 'span' })).toBeInTheDocument()

    act(() => fake.current!.state.onChange!({ new: job({ status: 'live', phase: 'live', show_id: 42 }) }))

    expect(await screen.findByRole('link', { name: 'See the show' })).toHaveAttribute('href', '/shows/42/')
    expect(screen.getByText('Live', { selector: 'span' })).toBeInTheDocument()
  })

  it('marks the step a job failed at, with why', async () => {
    fake.current!.state.jobs = [
      job({ provider: 'screenshot', url: null, screenshot_path: 'u/1.png', status: 'failed', phase: 'reading_screenshot',
            message: 'The Chapel is in Portland, not a Bay Area city we know',
            extracted: { performers: ['Wet Leg'], venue: 'The Chapel', city: 'Portland', month: 12, day: 5, year: null } }),
    ]
    render(<AdminPage />)

    expect(await screen.findByText(/not a Bay Area city/)).toBeInTheDocument()
    expect(screen.getByLabelText('failed').closest('li')).toHaveTextContent('Reading')
    expect(screen.getByText('Read: Wet Leg · The Chapel, Portland · 12/5')).toBeInTheDocument()
  })

  it('reads the jobs again now and then while Realtime is down and a job is on its way', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    fake.current!.state.realtime = 'CHANNEL_ERROR'
    fake.current!.state.jobs = [job({ status: 'running', phase: 'venue' })]
    render(<AdminPage />)
    await screen.findByText('Running')
    const reads = fake.current!.client.from.mock.calls.length

    fake.current!.state.jobs = [job({ status: 'added', phase: 'committing', detail: 'Committing the data branch' })]
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })

    expect(fake.current!.client.from.mock.calls.length).toBeGreaterThan(reads)
    expect(await screen.findByText('Committing the data branch')).toBeInTheDocument()
  })
})

describe('readLine', () => {
  it('says what the model read, leaving out what it did not', () => {
    expect(readLine({ performers: ['A', 'B'], venue: 'V', city: null, month: 1, day: 2, year: 2027 })).toBe('A, B · V · 1/2/2027')
    expect(readLine({})).toBeNull()
    expect(readLine(null)).toBeNull()
  })
})
