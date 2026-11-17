import { supabase } from './supabase'

/**
 * The Admin page's ingest jobs (docs/adr/0006-admin-ingest-jobs.md): Shows an admin asked for, one per link to an
 * event's page or screenshot. They're added through the admin Edge Function (supabase/functions/admin), run by the Ingest jobs
 * workflow, and read back from Supabase's ingest_jobs table, which says how far each has got.
 */

export type JobStatus = 'queued' | 'running' | 'added' | 'live' | 'failed'

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
    provider === 'screenshot' ? { id: 'reading_screenshot', label: 'Reading' } : { id: 'fetching_page', label: 'Fetching' },
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

/** Each job's changes as they're made (Supabase Realtime); `onState` hears whether that's working. */
export function watchJobs(onChange: (job: IngestJob) => void, onState: (live: boolean) => void): () => void {
  const client = supabase
  if (!client) return () => {}
  const channel = client
    .channel('ingest-jobs')
    .on('postgres_changes', { event: '*', schema: 'public', table: 'ingest_jobs' }, payload => {
      if (payload.new && 'id' in payload.new) onChange(payload.new as IngestJob)
    })
    .subscribe(status => onState(status === 'SUBSCRIBED'))
  return () => {
    client.removeChannel(channel)
  }
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
