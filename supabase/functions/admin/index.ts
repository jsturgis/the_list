/**
 * The Admin page's API (docs/adr/0006-admin-ingest-jobs.md).
 *
 *   POST /functions/v1/admin/v1/shows   multipart form: `url` (any number, TicketWeb event links) and `screenshot`
 *                                       (any number, images of events), with the signed-in admin's session token
 *
 * Each valid link or screenshot becomes an ingest job: a row in ingest_jobs and a message on the ingest_jobs queue
 * (enqueue_ingest_job, supabase/migrations/0004_ingest_jobs.sql). Screenshots go in the ingest-screenshots bucket
 * first. Everything is done as the caller, so the database's policies decide what an admin may do.
 *
 * Answers { jobs: [...], rejected: [{ input, reason }] }; 401 without a session, 403 for someone who isn't an admin.
 * Deploy: supabase functions deploy admin
 */
import { createClient, type SupabaseClient } from 'npm:@supabase/supabase-js@2.117.2'
import { checkEventUrl, isAdmin, SCREENSHOT_MAX_BYTES, SCREENSHOT_TYPES } from '../_shared/eventUrls.ts'
import { sniffImageType } from '../_shared/images.ts'

const ALLOWED_ORIGINS = ['https://list.sturgis.me', 'http://localhost:3000']
const MAX_ITEMS = 20
const EXTENSIONS: Record<string, string> = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp' }

function cors(request: Request): Record<string, string> {
  const origin = request.headers.get('Origin') ?? ''
  return {
    'Access-Control-Allow-Origin': ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
    'Access-Control-Allow-Headers': 'authorization, apikey, content-type, x-client-info',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    Vary: 'Origin',
  }
}

function json(request: Request, status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...cors(request), 'Content-Type': 'application/json' },
  })
}

type Rejected = { input: string; reason: string }

async function enqueue(client: SupabaseClient, args: Record<string, string>) {
  const { data, error } = await client.rpc('enqueue_ingest_job', args)
  if (error) throw new Error(error.message)
  return data
}

async function addShows(request: Request, client: SupabaseClient, userId: string): Promise<Response> {
  let form: FormData
  try {
    form = await request.formData()
  } catch {
    return json(request, 400, { error: 'Send a form with url and screenshot fields' })
  }
  const urls = form.getAll('url').flatMap(v => (typeof v === 'string' ? v.split(/\s+/) : [])).filter(Boolean)
  const screenshots = form.getAll('screenshot').filter((v): v is File => v instanceof File)
  if (urls.length + screenshots.length === 0) return json(request, 400, { error: 'Nothing to add' })
  if (urls.length + screenshots.length > MAX_ITEMS) {
    return json(request, 400, { error: `Add at most ${MAX_ITEMS} links and screenshots at a time` })
  }

  const jobs = []
  const rejected: Rejected[] = []
  for (const input of urls) {
    const check = checkEventUrl(input)
    if (!check.ok) {
      rejected.push({ input, reason: check.reason })
      continue
    }
    jobs.push(await enqueue(client, { provider: check.provider, url: check.url }))
  }
  for (const file of screenshots) {
    if (!SCREENSHOT_TYPES.includes(file.type)) {
      rejected.push({ input: file.name, reason: 'is not a PNG, JPEG or WebP image' })
      continue
    }
    if (file.size > SCREENSHOT_MAX_BYTES) {
      rejected.push({ input: file.name, reason: 'is over 10 MB' })
      continue
    }
    // The type a file is sent with is only what it's named: its first bytes say what it is, and that's what's kept.
    const actual = sniffImageType(new Uint8Array(await file.slice(0, 12).arrayBuffer()))
    if (!actual) {
      rejected.push({ input: file.name, reason: "isn't really a PNG, JPEG or WebP image" })
      continue
    }
    const path = `${userId}/${crypto.randomUUID()}.${EXTENSIONS[actual]}`
    const { error } = await client.storage.from('ingest-screenshots').upload(path, file, { contentType: actual })
    if (error) {
      rejected.push({ input: file.name, reason: `couldn't be stored: ${error.message}` })
      continue
    }
    jobs.push(await enqueue(client, { provider: 'screenshot', screenshot_path: path }))
  }
  return json(request, 200, { jobs, rejected })
}

Deno.serve(async request => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: cors(request) })
  const path = new URL(request.url).pathname
  if (!path.endsWith('/v1/shows')) return json(request, 404, { error: 'Not found' })
  if (request.method !== 'POST') return json(request, 405, { error: 'Use POST' })

  const authorization = request.headers.get('Authorization') ?? ''
  if (!authorization.startsWith('Bearer ')) return json(request, 401, { error: 'Sign in first' })
  // As the caller: their session token goes with every request, so the database's policies apply to them.
  const client = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_ANON_KEY')!, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false },
  })
  const { data, error } = await client.auth.getUser(authorization.slice('Bearer '.length))
  if (error || !data.user) return json(request, 401, { error: 'Sign in first' })
  if (!isAdmin(data.user.app_metadata)) return json(request, 403, { error: 'Only admins can add Shows' })

  try {
    return await addShows(request, client, data.user.id)
  } catch (e) {
    console.error('admin: adding shows failed', e)
    return json(request, 500, { error: e instanceof Error ? e.message : String(e) })
  }
})
