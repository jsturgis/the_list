import { useCallback, useEffect, useMemo, useRef, useState, type ClipboardEvent, type DragEvent, type FormEvent } from 'react'
import { CheckIcon, PhotoIcon, TrashIcon, XMarkIcon } from '@heroicons/react/16/solid'
import { href } from '@/lib/basePath'
import { FIELD } from '@/lib/field'
import { checkEventUrl, SCREENSHOT_MAX_BYTES, SCREENSHOT_TYPES } from '@/lib/eventUrls'
import {
  addShows,
  approveJob,
  deletable,
  deleteJob,
  inProgress,
  loadJobs,
  phasesFor,
  readByModel,
  RECENT_JOBS,
  watchJobs,
  type AddResult,
  type IngestJob,
  type JobStatus,
  type ReadFields,
  screenshotUrl,
  showsLink,
  wantsScreenshot,
} from '@/lib/ingestJobs'
import { supabase } from '@/lib/supabase'
import { useSession } from '@/lib/useSession'
import { GhostLine, GhostRows, LoadingLabel } from './Ghost'
import PageHeader from './PageHeader'
import Section from './Section'
import SignInByEmail from './SignInByEmail'
import Toast from './Toast'

/** How often the jobs are read again while any is on its way and Realtime isn't telling the page about changes. */
export const POLL_MS = 10_000

const adminPageUrl = () => new URL(href('/admin/'), window.location.origin).toString()

/**
 * The Admin page (/admin/): add Shows from links to event pages and screenshots of events, and follow each ingest job to the
 * site. Only admins see it; the admin Edge Function and the database check again for everything it does.
 */
export default function AdminPage() {
  const session = useSession()

  return (
    <article className="flex flex-col gap-6">
      <PageHeader title="Admin" subtitle="Add shows the List doesn't have yet, from links to their pages or screenshots." />

      {session.status === 'loading' && (
        <div data-ghost="" className="flex flex-col gap-3">
          <LoadingLabel>Loading…</LoadingLabel>
          <GhostLine className="h-7 w-32" />
          <div className="flex flex-col gap-3 rounded-lg bg-surface p-5">
            <GhostLine className="w-3/4" />
            <GhostLine className="h-24 w-full" />
          </div>
        </div>
      )}
      {session.status === 'unavailable' && (
        <p className="text-sm text-ink-muted">The Admin page isn&apos;t available on this copy of the site.</p>
      )}
      {session.status === 'signedOut' && (
        <SignInByEmail redirectTo={adminPageUrl} intro="Admins only. We'll email you a link to sign in." />
      )}
      {session.status === 'signedIn' && !session.isAdmin && (
        <div className="flex flex-col gap-3">
          <p role="alert" className="text-sm text-ink-soft">
            You&apos;re signed in as {session.email}, which isn&apos;t an admin. If you were just made one, sign out and
            in again.
          </p>
          <SignOut />
        </div>
      )}
      {session.status === 'signedIn' && session.isAdmin && <Admin email={session.email} />}
    </article>
  )
}

function SignOut() {
  return (
    <button type="button" onClick={() => supabase?.auth.signOut()} className="w-fit text-sm text-ink-muted underline hover:text-ink-soft">
      Sign out
    </button>
  )
}

function Admin({ email }: { email: string }) {
  const [jobs, setJobs] = useState<IngestJob[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState(false)

  const refresh = useCallback(
    () =>
      loadJobs().then(
        loaded => {
          setJobs(loaded)
          setError(null)
        },
        (e: unknown) => setError(e instanceof Error ? e.message : String(e)),
      ),
    [],
  )

  // The latest jobs, then each change to one as it's made, merged into the list.
  useEffect(() => {
    let cancelled = false
    loadJobs().then(
      loaded => {
        if (!cancelled) setJobs(loaded)
      },
      (e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      },
    )
    const stop = watchJobs(
      job =>
        setJobs(current => {
          const rest = (current ?? []).filter(j => j.id !== job.id)
          return [job, ...rest].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, RECENT_JOBS)
        }),
      setLive,
      id => setJobs(current => current?.filter(j => j.id !== id) ?? current),
    )
    return () => {
      cancelled = true
      stop()
    }
  }, [])

  // Without Realtime, read them again now and then while any is on its way.
  const waiting = jobs?.some(inProgress) ?? false
  useEffect(() => {
    if (live || !waiting) return
    const timer = setInterval(refresh, POLL_MS)
    return () => clearInterval(timer)
  }, [live, waiting, refresh])

  const [toast, setToast] = useState<string | null>(null)
  const dismissToast = useCallback(() => setToast(null), [])
  const remove = async (job: IngestJob) => {
    try {
      await deleteJob(job)
      setJobs(current => current?.filter(j => j.id !== job.id) ?? current)
      setToast(`Deleted the job for ${jobTitle(job)}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const added = (result: AddResult) =>
    setJobs(current => {
      const ids = new Set(result.jobs.map(j => j.id))
      return [...result.jobs, ...(current ?? []).filter(j => !ids.has(j.id))].slice(0, RECENT_JOBS)
    })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4 text-sm text-ink-muted">
        <span>Signed in as {email}</span>
        <SignOut />
      </div>
      <AddShowsForm onAdded={added} />
      <Section title="Jobs" aside={jobs?.length ? `Latest ${jobs.length}` : undefined}>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        {jobs === null && !error ? (
          <GhostRows label="Loading jobs…" />
        ) : jobs?.length === 0 ? (
          <p className="text-sm text-ink-soft">No jobs yet. Shows you add appear here as they make their way to the site.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line-subtle">
            {jobs?.map(job => <JobRow key={job.id} job={job} onDelete={() => remove(job)} />)}
          </ul>
        )}
      </Section>
      {toast && <Toast onDismiss={dismissToast}>{toast}</Toast>}
    </div>
  )
}

// ── Adding ────────────────────────────────────────────────────────────────────

function screenshotProblem(file: File): string | null {
  if (!SCREENSHOT_TYPES.includes(file.type)) return 'isn’t a PNG, JPEG or WebP image'
  if (file.size > SCREENSHOT_MAX_BYTES) return 'is over 10 MB'
  return null
}

function AddShowsForm({ onAdded }: { onAdded: (result: AddResult) => void }) {
  const [text, setText] = useState('')
  const [screenshots, setScreenshots] = useState<File[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rejected, setRejected] = useState<AddResult['rejected']>([])
  const [toast, setToast] = useState<string | null>(null)
  const dismissToast = useCallback(() => setToast(null), [])
  const fileInput = useRef<HTMLInputElement>(null)

  const lines = useMemo(() => text.split('\n').map(l => l.trim()).filter(Boolean), [text])
  const checks = lines.map(line => ({ line, check: checkEventUrl(line) }))
  const badScreenshots = screenshots.map(screenshotProblem)
  const ready = checks.some(c => c.check.ok) || screenshots.some((_, i) => !badScreenshots[i])

  const addFiles = (files: Iterable<File>) => {
    const images = [...files].filter(f => f.type.startsWith('image/'))
    if (images.length) setScreenshots(current => [...current, ...images])
  }
  const paste = (e: ClipboardEvent) => {
    const files = [...e.clipboardData.files]
    if (files.some(f => f.type.startsWith('image/'))) {
      e.preventDefault()
      addFiles(files)
    }
  }
  // Screenshots dropped anywhere on the form; the drop zone lights up while files are dragged over it.
  const [dragging, setDragging] = useState(false)
  const carriesFiles = (e: DragEvent) => [...e.dataTransfer.types].includes('Files')
  const dragOver = (e: DragEvent) => {
    if (!carriesFiles(e)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
    setDragging(true)
  }
  const dragLeave = (e: DragEvent) => {
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false)
  }
  const drop = (e: DragEvent) => {
    if (!carriesFiles(e)) return
    e.preventDefault()
    setDragging(false)
    addFiles(e.dataTransfer.files)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const urls = checks.filter(c => c.check.ok).map(c => c.line)
    const files = screenshots.filter((_, i) => !badScreenshots[i])
    setSending(true)
    setError(null)
    try {
      const result = await addShows(urls, files)
      onAdded(result)
      setRejected(result.rejected)
      // Keep what wasn't added, to fix and send again.
      const refused = new Set(result.rejected.map(r => r.input))
      setText(checks.filter(c => !c.check.ok || refused.has(c.line)).map(c => c.line).join('\n'))
      setScreenshots(current => current.filter((f, i) => badScreenshots[i] || refused.has(f.name)))
      if (result.jobs.length) setToast(`Added ${result.jobs.length} job${result.jobs.length === 1 ? '' : 's'}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSending(false)
    }
  }

  return (
    <Section title="Add shows">
      <form onSubmit={submit} onPaste={paste} onDragOver={dragOver} onDragLeave={dragLeave} onDrop={drop} className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <label htmlFor="admin-links" className="text-sm font-semibold text-ink">
            Event links
          </label>
          <textarea
            id="admin-links"
            rows={4}
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder="https://…"
            aria-describedby="admin-links-help"
            className="rounded-lg border border-line-strong bg-field px-3 py-2 text-base text-ink placeholder:text-ink-faint"
          />
          <p id="admin-links-help" className="text-xs text-ink-muted">
            One per line, to the event&apos;s page on any site: TicketWeb, a venue&apos;s site, Eventbrite… If a site
            won&apos;t let its page be read, the job asks for a screenshot instead.
          </p>
          {checks.length > 0 && (
            <ul aria-label="Links" className="flex flex-col gap-1 text-sm">
              {checks.map(({ line, check }, i) => (
                <li key={`${i}-${line}`} className="flex min-w-0 items-start gap-2">
                  {check.ok ? (
                    <CheckIcon aria-label="Ready" className="mt-0.5 size-4 shrink-0 text-success" />
                  ) : (
                    <XMarkIcon aria-label="Won't be added" className="mt-0.5 size-4 shrink-0 text-danger" />
                  )}
                  <span className="min-w-0 break-all text-ink-soft">
                    {line}
                    {!check.ok && <span className="text-danger"> {check.reason}</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <span id="admin-screenshots" className="text-sm font-semibold text-ink">
            Screenshots
          </span>
          <div
            id="admin-drop-zone"
            data-dragging={dragging || undefined}
            className={`flex flex-col items-center gap-3 rounded-lg border-2 border-dashed px-4 py-6 text-center ${
              dragging ? 'border-accent bg-accent-soft text-accent-soft-ink' : 'border-line-strong text-ink-muted'
            }`}
          >
            {screenshots.length > 0 ? (
              <ul aria-labelledby="admin-screenshots" className="grid w-full grid-cols-2 gap-3 text-left sm:grid-cols-3">
                {screenshots.map((file, i) => (
                  <ScreenshotPreview
                    key={`${i}-${file.name}-${file.lastModified}`}
                    file={file}
                    problem={badScreenshots[i]}
                    onRemove={() => setScreenshots(current => current.filter((_, j) => j !== i))}
                  />
                ))}
              </ul>
            ) : (
              <PhotoIcon aria-hidden="true" className={`size-6 ${dragging ? '' : 'text-ink-faint'}`} />
            )}
            <p className="text-sm">
              {dragging ? 'Drop to add' : screenshots.length > 0 ? 'Drag more here, paste one, or' : 'Drag screenshots here, paste one, or'}
            </p>
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              data-choose-screenshots=""
              className="h-9 w-fit rounded-full border border-line-strong bg-surface px-4 text-sm font-bold text-ink hover:bg-muted"
            >
              Choose screenshots
            </button>
          </div>
          <p className="text-xs text-ink-muted">Each is read by a vision model: check the job to see what it read.</p>
          <input
            ref={fileInput}
            type="file"
            accept={SCREENSHOT_TYPES.join(',')}
            multiple
            className="sr-only"
            aria-labelledby="admin-screenshots"
            onChange={e => {
              addFiles(e.target.files ?? [])
              e.target.value = ''
            }}
          />
        </div>

        <button
          type="submit"
          disabled={sending || !ready}
          className="h-9 w-fit rounded-full bg-accent px-5 text-sm font-bold text-on-accent hover:bg-accent-hover disabled:opacity-50"
        >
          {sending ? 'Adding…' : 'Add shows'}
        </button>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        {rejected.length > 0 && (
          <div role="alert" className="flex flex-col gap-1 text-sm">
            <p className="font-semibold text-danger">Not added:</p>
            <ul className="flex flex-col gap-1">
              {rejected.map((r, i) => (
                <li key={`${i}-${r.input}`} className="break-all text-ink-soft">
                  {r.input} <span className="text-danger">{r.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </form>
      {toast && <Toast onDismiss={dismissToast}>{toast}</Toast>}
    </Section>
  )
}

/** A screenshot waiting to be added: the image itself, its name, and a button to take it out again. */
function ScreenshotPreview({ file, problem, onRemove }: { file: File; problem: string | null; onRemove: () => void }) {
  // The file shown from memory; let go of when the preview goes.
  const src = useMemo(() => URL.createObjectURL(file), [file])
  useEffect(() => () => URL.revokeObjectURL(src), [src])

  return (
    <li className="relative flex min-w-0 flex-col gap-1">
      <div className="aspect-[4/3] overflow-hidden rounded-lg border border-line bg-muted">
        {!problem && <img src={src} alt={`Preview of ${file.name}`} className="size-full object-contain" />}
        {problem && (
          <div className="flex size-full items-center justify-center p-2 text-center text-xs text-danger">{problem}</div>
        )}
      </div>
      <span className="truncate text-xs text-ink-muted" title={file.name}>
        {file.name}
      </span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${file.name}`}
        title="Remove"
        className="absolute right-1.5 top-1.5 rounded-full border border-line bg-surface p-1 text-ink-soft hover:bg-muted hover:text-ink"
      >
        <XMarkIcon className="size-4" />
      </button>
    </li>
  )
}

// ── Following ─────────────────────────────────────────────────────────────────

const STATUS: Record<JobStatus, { label: string; className: string }> = {
  queued: { label: 'Queued', className: 'bg-muted text-ink-soft' },
  running: { label: 'Running', className: 'bg-info-soft text-info' },
  review: { label: 'Needs review', className: 'bg-warning-soft text-warning' },
  added: { label: 'Added', className: 'bg-accent-chip text-accent-chip-ink' },
  live: { label: 'Live', className: 'bg-success-soft text-success' },
  failed: { label: 'Failed', className: 'bg-danger-soft text-danger' },
}

function ago(iso: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - Date.parse(iso)) / 1000))
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return `${Math.floor(seconds / 86400)} d ago`
}

function jobTitle(job: IngestJob): string {
  if (job.provider === 'screenshot') return 'Screenshot'
  try {
    const url = new URL(job.url ?? '')
    if (job.provider === 'ticketweb') {
      return url.pathname.split('/').filter(Boolean)[1]?.replace(/-tickets$/, '').replace(/-/g, ' ') || url.hostname
    }
    return url.hostname.replace(/^www\./, '')
  } catch {
    return job.url ?? 'Link'
  }
}

/** Takes the admin to the screenshot drop zone, ready to choose one. */
function toScreenshots() {
  document.getElementById('admin-drop-zone')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  document.querySelector<HTMLElement>('[data-choose-screenshots]')?.focus({ preventScroll: true })
}

/** What the vision model read from a screenshot, in a line: "Wet Leg, Idles · The Chapel, San Francisco · Fri, Dec 5". */
export function readLine(extracted: Record<string, unknown> | null): string | null {
  if (!extracted) return null
  const performers = Array.isArray(extracted.performers) ? extracted.performers.filter(p => typeof p === 'string') : []
  const where = [extracted.venue, extracted.city].filter(v => typeof v === 'string' && v).join(', ')
  // The date as the screenshot writes it (older jobs have it as numbers).
  const when = typeof extracted.date === 'string' && extracted.date
    ? extracted.date
    : [extracted.month, extracted.day, extracted.year].filter(v => typeof v === 'number').join('/')
  const parts = [performers.join(', '), where, when].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

const isUrl = (text: string | null): text is string => !!text && /^https?:\/\//.test(text)

/** The screenshot a job was added from, to check what the model read against: a thumbnail that opens it full size. */
function JobScreenshot({ path }: { path: string }) {
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    screenshotUrl(path).then(url => {
      if (!cancelled) setSrc(url)
    })
    return () => {
      cancelled = true
    }
  }, [path])
  if (!src) return null
  return (
    <a href={src} target="_blank" rel="noreferrer" className="block w-fit" title="Open the screenshot">
      <img src={src} alt="The screenshot this job was added from" className="max-h-40 w-auto rounded-lg border border-line" />
    </a>
  )
}

const REVIEW_FIELDS: { key: Exclude<keyof ReadFields, 'performers'>; label: string; placeholder: string }[] = [
  { key: 'venue', label: 'Venue', placeholder: 'The Chapel' },
  { key: 'city', label: 'City', placeholder: 'San Francisco' },
  { key: 'date', label: 'Date', placeholder: 'Fri, Dec 12' },
  { key: 'doors_time', label: 'Doors', placeholder: '7:00 PM' },
  { key: 'show_time', label: 'Show', placeholder: '8:00 PM' },
  { key: 'price', label: 'Price', placeholder: '$20 - $25' },
  { key: 'age', label: 'Age', placeholder: '21+' },
  { key: 'status', label: 'Status', placeholder: 'Sold Out, Cancelled…' },
]

const text = (value: unknown) => (typeof value === 'string' ? value : '')

/**
 * A job waiting for review: what a model read, from a screenshot (to check against the screenshot above it) or from
 * a link's page that has no schema.org event (against the page it links to), to correct. Approve queues it to be added
 * as it stands here; Discard deletes it. Nothing a model read reaches the site without this.
 */
function ReviewForm({ job, onDiscard }: { job: IngestJob; onDiscard: () => void }) {
  const read = job.extracted ?? {}
  const [lineup, setLineup] = useState(() =>
    (Array.isArray(read.performers) ? read.performers.filter(p => typeof p === 'string') : []).join('\n'),
  )
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(REVIEW_FIELDS.map(({ key }) => [key, text(read[key])])),
  )
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const performers = lineup.split('\n').map(l => l.trim()).filter(Boolean)
  const ready = performers.length > 0 && values.venue.trim() !== '' && values.date.trim() !== ''

  const approve = async (e: FormEvent) => {
    e.preventDefault()
    setSending(true)
    setError(null)
    try {
      const fields = Object.fromEntries(REVIEW_FIELDS.map(({ key }) => [key, values[key].trim() || null]))
      await approveJob(job.id, { performers, ...fields } as ReadFields)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSending(false)
    }
  }

  const id = (key: string) => `review-${job.id}-${key}`
  return (
    <form onSubmit={approve} aria-label="Review what was read" className="flex flex-col gap-3 rounded-lg border border-line p-3">
      <div className="flex flex-col gap-1">
        <label htmlFor={id('lineup')} className="text-xs font-semibold text-ink">
          Lineup, headliner first, one per line
        </label>
        <textarea
          id={id('lineup')}
          rows={Math.max(2, performers.length + 1)}
          value={lineup}
          onChange={e => setLineup(e.target.value)}
          className="rounded-lg border border-line-strong bg-field px-3 py-2 text-base text-ink placeholder:text-ink-faint"
        />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {REVIEW_FIELDS.map(({ key, label, placeholder }) => (
          <div key={key} className="flex flex-col gap-1">
            <label htmlFor={id(key)} className="text-xs font-semibold text-ink">
              {label}
            </label>
            <input
              id={id(key)}
              value={values[key]}
              placeholder={placeholder}
              onChange={e => setValues(v => ({ ...v, [key]: e.target.value }))}
              className={`${FIELD} px-3`}
            />
          </div>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={sending || !ready}
          className="h-9 rounded-full bg-accent px-5 text-sm font-bold text-on-accent hover:bg-accent-hover disabled:opacity-50"
        >
          {sending ? 'Approving…' : 'Approve and add'}
        </button>
        <button
          type="button"
          onClick={onDiscard}
          disabled={sending}
          className="h-9 rounded-full border border-line-strong px-4 text-sm font-bold text-ink hover:bg-muted disabled:opacity-50"
        >
          Discard
        </button>
      </div>
      {!ready && <p className="text-xs text-ink-muted">A lineup, a venue and a date are needed to add it.</p>}
    </form>
  )
}

function JobRow({ job, onDelete }: { job: IngestJob; onDelete: () => void }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!inProgress(job)) return
    const timer = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(timer)
  }, [job])
  const phases = phasesFor(job.provider, readByModel(job))
  const current = Math.max(0, phases.findIndex(p => p.id === job.phase))
  const failed = job.status === 'failed'
  const status = STATUS[job.status] ?? STATUS.queued
  const read = readLine(job.extracted)
  const link = showsLink(job)

  return (
    <li data-job={job.id} className="flex flex-col gap-2 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className={`inline-flex shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${status.className}`}>
            {status.label}
          </span>
          {job.url ? (
            <a href={job.url} target="_blank" rel="noreferrer" className={`min-w-0 truncate font-bold text-ink hover:underline ${job.provider === 'ticketweb' ? 'capitalize' : ''}`}>
              {jobTitle(job)}
            </a>
          ) : (
            <span className="font-bold text-ink">{jobTitle(job)}</span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-xs text-ink-muted">{ago(job.updated_at, now)}</span>
          {deletable(job) && (
            <button
              type="button"
              onClick={onDelete}
              aria-label={`Delete the job for ${jobTitle(job)}`}
              title="Delete"
              className="rounded-full p-1 text-ink-faint hover:bg-muted hover:text-danger"
            >
              <TrashIcon className="size-4" />
            </button>
          )}
        </div>
      </div>

      {job.screenshot_path && <JobScreenshot path={job.screenshot_path} />}
      {read && job.status !== 'review' && <p className="text-sm text-ink-soft">Read: {read}</p>}

      <ol aria-label="Steps" className="flex flex-wrap gap-1">
        {phases.map((phase, i) => {
          const done = job.status === 'live' || i < current
          const here = i === current && job.status !== 'live'
          const style = here
            ? failed
              ? 'bg-danger-soft text-danger font-semibold'
              : 'bg-accent-chip text-accent-chip-ink font-semibold'
            : done
              ? 'bg-muted text-ink-soft'
              : 'border border-line text-ink-muted'
          return (
            <li
              key={phase.id}
              aria-current={here ? 'step' : undefined}
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${style}`}
            >
              {done && <CheckIcon aria-label="done" className="size-3" />}
              {here && failed && <XMarkIcon aria-label="failed" className="size-3" />}
              {phase.label}
            </li>
          )
        })}
      </ol>

      {job.detail && !failed && job.status !== 'live' && (
        <p className="text-sm text-ink-muted">
          {isUrl(job.detail) ? (
            <a href={job.detail} target="_blank" rel="noreferrer" className="text-link underline underline-offset-2">
              {job.phase === 'deploying' ? 'The Deploy run' : job.detail}
            </a>
          ) : (
            job.detail
          )}
        </p>
      )}
      {job.message && (
        <p className={`text-sm ${failed ? 'text-danger' : job.status === 'review' ? 'text-warning' : 'text-ink-soft'}`}>
          {job.message}
        </p>
      )}
      {job.status === 'review' && <ReviewForm job={job} onDiscard={onDelete} />}
      {wantsScreenshot(job) && (
        <button
          type="button"
          onClick={toScreenshots}
          className="h-9 w-fit rounded-full border border-line-strong px-4 text-sm font-bold text-ink hover:bg-muted"
        >
          Add a screenshot instead
        </button>
      )}

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {link && (
          <a href={href(link.path)} className="font-bold text-link underline underline-offset-2">
            {link.label}
          </a>
        )}
        {job.workflow_run_url && (
          <a href={job.workflow_run_url} target="_blank" rel="noreferrer" className="text-ink-muted underline hover:text-ink-soft">
            Workflow run
          </a>
        )}
        {job.attempts > 1 && <span className="text-ink-muted">Attempt {job.attempts}</span>}
      </div>
    </li>
  )
}
