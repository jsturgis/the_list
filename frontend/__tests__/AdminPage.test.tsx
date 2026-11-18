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
    onChange: null as ((payload: { eventType?: string; new?: IngestJob; old?: { id: string } }) => void) | null,
  }
  const deleteJob = vi.fn(async (_column: string, id: string) => {
    const deleted = state.jobs.filter(j => j.id === id && ['failed', 'live', 'review'].includes(j.status))
    state.jobs = state.jobs.filter(j => !deleted.includes(j))
    return { data: deleted.map(j => ({ id: j.id })), error: null }
  })
  const removeScreenshot = vi.fn<(paths: string[]) => Promise<{ data: []; error: null }>>(async () => ({ data: [], error: null }))
  // approve_ingest_job: a job waiting for review, queued again with its fields as approved.
  const rpc = vi.fn(async (fn: string, args: { job_id: string; fields: Record<string, unknown> }) => {
    if (fn !== 'approve_ingest_job') throw new Error(`unexpected function ${fn}`)
    const found = state.jobs.find(j => j.id === args.job_id && j.status === 'review')
    if (!found) return { data: null, error: { message: 'That job isn\'t waiting for review' } }
    Object.assign(found, { status: 'queued', phase: 'queued', extracted: args.fields, message: null })
    return { data: { ...found }, error: null }
  })
  const client = {
    rpc,
    deleteJob,
    removeScreenshot,
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
      return {
        select: () => ({ order: () => ({ limit: async () => ({ data: [...state.jobs], error: null }) }) }),
        // As the database's policy: only finished jobs are deleted; the rows deleted come back.
        delete: () => ({
          eq: (column: string, id: string) => ({ select: () => deleteJob(column, id) }),
        }),
      }
    }),
    channel: vi.fn(() => {
      const channel = {
        on: (_event: string, _filter: unknown, listener: NonNullable<typeof state.onChange>) => {
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
    storage: {
      from: vi.fn(() => ({
        createSignedUrl: vi.fn(async (path: string) => ({ data: { signedUrl: `https://signed.example/${path}` }, error: null })),
        remove: removeScreenshot,
      })),
    },
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
  // Not in jsdom: a preview's image comes from memory.
  URL.createObjectURL = vi.fn((file: Blob) => `blob:preview/${(file as File).name}`)
  URL.revokeObjectURL = vi.fn()
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

  it('lets a screenshot be taken out again, letting go of its preview', async () => {
    render(<AdminPage />)
    fireEvent.change(await screen.findByLabelText('Screenshots'), {
      target: { files: [new File(['png'], 'event.png', { type: 'image/png' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Remove event.png' }))

    expect(screen.queryByRole('img', { name: 'Preview of event.png' })).not.toBeInTheDocument()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview/event.png')
  })

  it('says why a screenshot it can’t take is refused, instead of showing it', async () => {
    render(<AdminPage />)
    fireEvent.change(await screen.findByLabelText('Screenshots'), {
      target: { files: [new File(['gif'], 'event.gif', { type: 'image/gif' })] },
    })

    expect(screen.getByText(/isn.t a PNG, JPEG or WebP image/)).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'Preview of event.gif' })).not.toBeInTheDocument()
  })

  it('shows the screenshot a job was added from, to check what was read', async () => {
    fake.current!.state.jobs = [job({ provider: 'screenshot', url: null, screenshot_path: 'user-1/a.png', status: 'running', phase: 'reading_screenshot' })]
    render(<AdminPage />)

    const image = await screen.findByRole('img', { name: 'The screenshot this job was added from' })
    expect(image).toHaveAttribute('src', 'https://signed.example/user-1/a.png')
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
    const preview = screen.getByRole('img', { name: 'Preview of event.png' })
    expect(preview).toHaveAttribute('src', 'blob:preview/event.png')
    expect(preview.closest('#admin-drop-zone')).not.toBeNull()   // shown inside the drop zone
    expect(screen.getByText('Drag more here, paste one, or')).toBeInTheDocument()
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

describe('Admin page, deleting jobs', () => {
  beforeEach(() => {
    fake.current!.state.user = ADMIN
  })

  it('clears a job from the database with its trash can, and its screenshot from storage', async () => {
    fake.current!.state.jobs = [
      job({ status: 'failed' }),
      job({ id: 'job-2', provider: 'screenshot', url: null, screenshot_path: 'user-1/a.png', status: 'failed', phase: 'reading_screenshot' }),
    ]
    render(<AdminPage />)

    fireEvent.click(await screen.findByRole('button', { name: 'Delete the job for Screenshot' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Deleted the job for Screenshot')
    expect(fake.current!.client.deleteJob).toHaveBeenCalledWith('id', 'job-2')
    expect(fake.current!.client.removeScreenshot).toHaveBeenCalledWith(['user-1/a.png'])
    expect(screen.queryByRole('button', { name: 'Delete the job for Screenshot' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /delete the job for wet leg the chapel/i })).toBeInTheDocument()
  })

  it('offers the trash can only on finished jobs: failed, or live', async () => {
    fake.current!.state.jobs = (['queued', 'running', 'added', 'failed', 'live'] as const).map(status =>
      job({ id: status, url: `https://www.ticketweb.com/event/${status}-show-tickets/1`, status }),
    )
    render(<AdminPage />)
    await screen.findByRole('link', { name: /queued show/i })

    const offered = screen.getAllByRole('button', { name: /^delete the job for/i }).map(b => b.getAttribute('aria-label'))
    expect(offered).toEqual(['Delete the job for failed show', 'Delete the job for live show'])
  })

  it('says so when the database won’t delete a job (it got going in the meantime)', async () => {
    fake.current!.state.jobs = [job({ status: 'failed' })]
    render(<AdminPage />)
    const trash = await screen.findByRole('button', { name: /delete the job for wet leg the chapel/i })
    fake.current!.state.jobs = [job({ status: 'running' })]   // retried by the worker since the page loaded

    fireEvent.click(trash)

    expect(await screen.findByRole('alert')).toHaveTextContent('Only finished jobs (failed, or live) and those waiting for review can be deleted')
  })

  it('leaves storage alone for a link’s job', async () => {
    fake.current!.state.jobs = [job({ status: 'live', phase: 'live', show_id: 1 })]
    render(<AdminPage />)

    fireEvent.click(await screen.findByRole('button', { name: /delete the job for wet leg the chapel/i }))

    await waitFor(() => expect(fake.current!.client.deleteJob).toHaveBeenCalledWith('id', 'job-1'))
    expect(fake.current!.client.removeScreenshot).not.toHaveBeenCalled()
    expect(await screen.findByText(/no jobs yet/i)).toBeInTheDocument()
  })

  it('drops a job deleted elsewhere (another admin, another tab)', async () => {
    fake.current!.state.jobs = [job({ status: 'failed' })]
    render(<AdminPage />)
    await screen.findByRole('button', { name: /delete the job for wet leg the chapel/i })

    act(() => fake.current!.state.onChange!({ eventType: 'DELETE', old: { id: 'job-1' } }))

    expect(await screen.findByText(/no jobs yet/i)).toBeInTheDocument()
  })
})

describe('Admin page, reviewing a screenshot', () => {
  const READ = {
    performers: ["Hell's Belles - World Famous All-Female AC/DC Tribute Band", 'murdershow'],
    venue: "Moe's Alley", city: 'Santa Cruz', date: null, doors_time: '8:00 PM', show_time: '9:00 PM',
    price: '$30', age: '21+', status: null,
  }
  const waiting = () =>
    job({ id: 'job-9', provider: 'screenshot', url: null, screenshot_path: 'user-1/a.png', status: 'review', phase: 'review',
          message: 'Check what was read: no date on the screenshot', extracted: READ })

  beforeEach(() => {
    fake.current!.state.user = ADMIN
    fake.current!.state.jobs = [waiting()]
  })

  it('shows what was read, to check against the screenshot, and why it can’t be added as it is', async () => {
    render(<AdminPage />)

    const form = await screen.findByRole('form', { name: 'Review what was read' })
    expect(screen.getByText('Needs review')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'The screenshot this job was added from' })).toBeInTheDocument()
    expect(screen.getByText('Check what was read: no date on the screenshot')).toBeInTheDocument()
    expect(within(form).getByLabelText(/lineup/i)).toHaveValue(READ.performers.join('\n'))
    expect(within(form).getByLabelText('Venue')).toHaveValue("Moe's Alley")
    expect(within(form).getByLabelText('Date')).toHaveValue('')
    // A date is needed before it can be approved.
    expect(within(form).getByRole('button', { name: 'Approve and add' })).toBeDisabled()
    expect(within(screen.getByRole('list', { name: 'Steps' })).getByText('Review').closest('li')).toHaveAttribute('aria-current', 'step')
  })

  it('approves it with the corrections, which queues it to be added', async () => {
    render(<AdminPage />)
    const form = await screen.findByRole('form', { name: 'Review what was read' })

    fireEvent.change(within(form).getByLabelText(/lineup/i), { target: { value: "Hell's Belles\nMurdershow\n" } })
    fireEvent.change(within(form).getByLabelText('Date'), { target: { value: 'Fri, Dec 12' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Approve and add' }))

    await waitFor(() => expect(fake.current!.client.rpc).toHaveBeenCalled())
    expect(fake.current!.client.rpc).toHaveBeenCalledWith('approve_ingest_job', {
      job_id: 'job-9',
      fields: { ...READ, performers: ["Hell's Belles", 'Murdershow'], date: 'Fri, Dec 12' },
    })
    // Realtime brings the change back: queued, no form.
    act(() => fake.current!.state.onChange!({ new: { ...waiting(), status: 'queued', phase: 'queued', message: null } }))
    expect(await screen.findByText('Queued', { selector: 'span' })).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Review what was read' })).not.toBeInTheDocument()
  })

  it('says why when it can’t be approved', async () => {
    render(<AdminPage />)
    const form = await screen.findByRole('form', { name: 'Review what was read' })
    fireEvent.change(within(form).getByLabelText('Date'), { target: { value: 'Dec 12' } })
    fake.current!.state.jobs = []   // discarded in another tab meanwhile

    fireEvent.click(within(form).getByRole('button', { name: 'Approve and add' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent("That job isn't waiting for review")
  })

  it('discards it, with its screenshot', async () => {
    render(<AdminPage />)
    const form = await screen.findByRole('form', { name: 'Review what was read' })

    fireEvent.click(within(form).getByRole('button', { name: 'Discard' }))

    await waitFor(() => expect(fake.current!.client.deleteJob).toHaveBeenCalledWith('id', 'job-9'))
    expect(fake.current!.client.removeScreenshot).toHaveBeenCalledWith(['user-1/a.png'])
    expect(await screen.findByText(/no jobs yet/i)).toBeInTheDocument()
  })
})

describe('readLine', () => {
  it('says what the model read, leaving out what it did not', () => {
    expect(readLine({ performers: ['A', 'B'], venue: 'V', city: null, month: 1, day: 2, year: 2027 })).toBe('A, B · V · 1/2/2027')
    expect(readLine({ performers: ['A'], venue: 'V', city: 'C', date: 'Fri, Dec 12' })).toBe('A · V, C · Fri, Dec 12')
    expect(readLine({})).toBeNull()
    expect(readLine(null)).toBeNull()
  })
})
