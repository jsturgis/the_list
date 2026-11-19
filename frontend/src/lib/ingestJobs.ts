import { supabase } from './supabase'

/**
 * The Admin page's ingest jobs (docs/adr/0006-admin-ingest-jobs.md): Shows an admin asked for, one per link to an
 * event's page or screenshot. They're added through the admin Edge Function (supabase/functions/admin), run by the Ingest jobs
 * workflow, and read back from Supabase's ingest_jobs table, which says how far each has got.
 */

export type JobStatus = 'queued' | 'running' | 'review' | 'added' | 'live' | 'failed'

export interface IngestJob {
  id: string
  provider: 'ticketweb' | 'page' | 'screenshot'
  url: string | null
  screenshot_path: string | null
  status: JobStatus
  phase: string
  detail: string | null
  message: string | null
  extracted: Record<string, unknown> | null
  show_id: number | null
  /** The Shows list's filter that picks out the Shows a job added, when it added several (an artist's page):
   * "bandId=12&fromDate=2027-01-21&toDate=2027-01-24". Missing before supabase/migrations/0008. */
  shows_query?: string | null
  workflow_run_url: string | null
  attempts: number
  created_at: string
  updated_at: string
}

export interface Phase {
  id: string
  label: string
}

/** The steps a job goes through, in order, as its `phase` names them. */
export function phasesFor(provider: IngestJob['provider']): Phase[] {
  return [
    { id: 'queued', label: 'Queued' },
    { id: 'dispatched', label: 'Dispatched' },
    ...(provider === 'screenshot'
      ? [{ id: 'reading_screenshot', label: 'Reading' }, { id: 'review', label: 'Review' }]
      : [{ id: 'fetching_page', label: 'Fetching' }]),
    { id: 'venue', label: 'Venue' },
    { id: 'bands', label: 'Bands' },
    { id: 'photos', label: 'Photos' },
    { id: 'saving', label: 'Saving' },
    { id: 'embedding', label: 'Embedding' },
    { id: 'committing', label: 'Committing' },
    { id: 'deploying', label: 'Deploying' },
    { id: 'live', label: 'Live' },
  ]
}

/** Whether the job is still on its way (so the page keeps it up to date). */
export function inProgress(job: Pick<IngestJob, 'status'>): boolean {
  return job.status === 'queued' || job.status === 'running' || job.status === 'added'
}

/** Whether a link's job failed because its page couldn't be read, so a screenshot of the event is the way to add it
 * (the workflow's message ends with this; backend/app/ingest_jobs.py). */
export const SCREENSHOT_INSTEAD = 'Take a screenshot of the event and add that instead.'

export function wantsScreenshot(job: Pick<IngestJob, 'status' | 'provider' | 'message'>): boolean {
  return job.status === 'failed' && job.provider !== 'screenshot' && (job.message ?? '').endsWith(SCREENSHOT_INSTEAD)
}

export const RECENT_JOBS = 25

export async function loadJobs(): Promise<IngestJob[]> {
  if (!supabase) return []
  const { data, error } = await supabase
    .from('ingest_jobs')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(RECENT_JOBS)
  if (error) throw new Error(error.message)
  return data as IngestJob[]
}

/** Each job's changes as they're made (Supabase Realtime), and the ids of jobs deleted (by another admin, or in
 * another tab); `onState` hears whether that's working. */
export function watchJobs(
  onChange: (job: IngestJob) => void,
  onState: (live: boolean) => void,
  onDelete: (id: string) => void = () => {},
): () => void {
  const client = supabase
  if (!client) return () => {}
  const channel = client
    .channel('ingest-jobs')
    .on('postgres_changes', { event: '*', schema: 'public', table: 'ingest_jobs' }, payload => {
      if (payload.eventType === 'DELETE') {
        if (payload.old && 'id' in payload.old) onDelete(payload.old.id as string)
      } else if (payload.new && 'id' in payload.new) onChange(payload.new as IngestJob)
    })
    .subscribe(status => onState(status === 'SUBSCRIBED'))
  return () => {
    client.removeChannel(channel)
  }
}

/** Where a live job's Shows are on the site: the Shows list, filtered to them, for a job that added several; else
 * its one Show's page. Paths, for `href`. */
export function showsLink(job: Pick<IngestJob, 'status' | 'show_id' | 'shows_query'>): { path: string; label: string } | null {
  if (job.status !== 'live') return null
  if (job.shows_query) return { path: `/?${job.shows_query}`, label: 'See the shows' }
  if (job.show_id !== null) return { path: `/shows/${job.show_id}/`, label: 'See the show' }
  return null
}

/** Whether a job can be cleared away: it's finished, failed or live (the database allows no other). */
/** How long a job on its way can go without progress before it's taken to have stalled: its run was cancelled while
 * it waited, or broke off before it could say so. Matches supabase/migrations/0009_retry_ingest_jobs.sql. A Deploy
 * (the "deploying" step) takes about ten minutes. */
export const STALLED_MS = 30 * 60_000

/** Whether the job is on its way but hasn't moved for STALLED_MS. */
export function stalled(job: Pick<IngestJob, 'status' | 'updated_at'>, now: number): boolean {
  return inProgress(job) && now - Date.parse(job.updated_at) > STALLED_MS
}

/** Whether the Admin page offers to retry the job: it failed (its run errored or was cancelled, its page couldn't be
 * read, its Deploy failed), or it has stalled. */
export function retryable(job: Pick<IngestJob, 'status' | 'updated_at'>, now: number): boolean {
  return job.status === 'failed' || stalled(job, now)
}

/** Start a failed or stalled job over (retry_ingest_job, supabase/migrations/0009): queued again at once, its
 * attempts back to 0, for the worker to hand to a new run. */
export async function retryJob(id: string): Promise<IngestJob> {
  const client = supabase
  if (!client) throw new Error('Supabase isn’t set up on this copy of the site')
  const { data, error } = await client.rpc('retry_ingest_job', { job_id: id })
  if (error) throw new Error(error.message)
  return data as IngestJob
}

export function deletable(job: Pick<IngestJob, 'status'>): boolean {
  return job.status === 'failed' || job.status === 'live'
}

/** What the vision model read from a screenshot, and what an admin approves: the fields as the screenshot writes them
 * (backend/app/ingestion/screenshot.py). */
export interface ReadFields {
  performers: string[]
  venue: string | null
  city: string | null
  date: string | null
  doors_time: string | null
  show_time: string | null
  price: string | null
  age: string | null
  status: string | null
}

/** Approve a screenshot job waiting for review, with its fields as corrected, and queue it to be added
 * (approve_ingest_job, supabase/migrations/0007). */
export async function approveJob(id: string, fields: ReadFields): Promise<IngestJob> {
  const client = supabase
  if (!client) throw new Error('Supabase isn’t set up on this copy of the site')
  const { data, error } = await client.rpc('approve_ingest_job', { job_id: id, fields })
  if (error) throw new Error(error.message)
  return data as IngestJob
}

/**
 * Clear a finished job from the database (supabase/migrations/0006), or discard one waiting for review (0007), and a
 * screenshot job's screenshot from storage. The database deletes no other; for one, nothing is deleted and this says
 * so.
 */
export async function deleteJob(job: Pick<IngestJob, 'id' | 'screenshot_path'>): Promise<void> {
  const client = supabase
  if (!client) throw new Error('Supabase isn’t set up on this copy of the site')
  const { data, error } = await client.from('ingest_jobs').delete().eq('id', job.id).select('id')
  if (error) throw new Error(error.message)
  if (!data?.length) throw new Error('Only finished jobs (failed, or live) and those waiting for review can be deleted')
  // The screenshot is only of use to its job; a failure to remove it leaves a file nobody sees.
  if (job.screenshot_path) await client.storage.from('ingest-screenshots').remove([job.screenshot_path])
}

/** A link to a job's screenshot, good for an hour (the bucket is private; admins may read it), or null. */
export async function screenshotUrl(path: string): Promise<string | null> {
  if (!supabase) return null
  const { data, error } = await supabase.storage.from('ingest-screenshots').createSignedUrl(path, 3600)
  return error ? null : data.signedUrl
}

export interface AddResult {
  jobs: IngestJob[]
  rejected: { input: string; reason: string }[]
}

/** Ask for these links and screenshots to be added (POST /functions/v1/admin/v1/shows), as the signed-in admin. */
export async function addShows(urls: string[], screenshots: File[]): Promise<AddResult> {
  const client = supabase
  if (!client) throw new Error('Supabase isn’t set up on this copy of the site')
  const { data } = await client.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error('Sign in again')
  const form = new FormData()
  urls.forEach(url => form.append('url', url))
  screenshots.forEach(file => form.append('screenshot', file, file.name))
  const response = await fetch(`${import.meta.env.PUBLIC_SUPABASE_URL}/functions/v1/admin/v1/shows`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, apikey: import.meta.env.PUBLIC_SUPABASE_ANON_KEY ?? '' },
    body: form,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.error ?? `The server said ${response.status}`)
  return body as AddResult
}
