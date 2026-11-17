/**
 * The ingest worker (docs/adr/0006-admin-ingest-jobs.md): pg_cron calls it each minute while the ingest_jobs queue
 * has a message to hand out (kick_ingest_worker, supabase/migrations/0004_ingest_jobs.sql). It claims the queued
 * jobs (claim_ingest_jobs) and starts the Ingest jobs GitHub workflow (.github/workflows/ingest-jobs.yml) for them.
 *
 * A claimed job's message stays hidden on the queue for an hour. The workflow takes it off as each job finishes; if
 * the run never gets there (cancelled by a newer run in its concurrency group, or crashed), the message shows again
 * and the job is claimed again, up to three times. When GitHub won't start the workflow, the messages are shown
 * again in five minutes.
 *
 * Secrets (supabase secrets set ...): WORKER_SECRET, the value the cron sends in x-worker-secret (and keeps in
 * Vault as ingest_worker_secret); GITHUB_TOKEN, a fine-grained token with Actions: read and write on GITHUB_REPO
 * only; GITHUB_REPO, e.g. jsturgis/the_list.
 * Deploy: supabase functions deploy ingest-worker --no-verify-jwt   (the cron has no session; the secret is checked)
 */
import { createClient } from 'npm:@supabase/supabase-js@2.117.2'

const WORKFLOW = 'ingest-jobs.yml'
const RETRY_DISPATCH_SECONDS = 300

type Claimed = { job_id: string; msg_id: number }

function sameSecret(a: string, b: string): boolean {
  if (!a || a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return diff === 0
}

Deno.serve(async request => {
  if (!sameSecret(request.headers.get('x-worker-secret') ?? '', Deno.env.get('WORKER_SECRET') ?? '')) {
    return new Response('Forbidden', { status: 403 })
  }
  const db = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!, {
    auth: { persistSession: false },
  })
  const { data, error } = await db.rpc('claim_ingest_jobs')
  if (error) {
    console.error('ingest-worker: claiming jobs failed', error)
    return new Response(error.message, { status: 500 })
  }
  const claimed = (data ?? []) as Claimed[]
  if (claimed.length === 0) return Response.json({ dispatched: 0 })

  const jobs = claimed.map(c => `${c.job_id}:${c.msg_id}`).join(',')
  const response = await fetch(
    `https://api.github.com/repos/${Deno.env.get('GITHUB_REPO')}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${Deno.env.get('GITHUB_TOKEN')}`,
        'X-GitHub-Api-Version': '2022-11-28',
      },
      body: JSON.stringify({ ref: 'main', inputs: { jobs } }),
    },
  )
  const ids = claimed.map(c => c.job_id)
  if (!response.ok) {
    const why = `Couldn't start the workflow (GitHub said ${response.status}); trying again in a few minutes`
    console.error('ingest-worker:', why, await response.text())
    await db.from('ingest_jobs').update({ detail: why }).in('id', ids)
    await db.rpc('release_ingest_jobs', { msg_ids: claimed.map(c => c.msg_id), delay: RETRY_DISPATCH_SECONDS })
    return new Response(why, { status: 502 })
  }
  await db.from('ingest_jobs').update({ detail: 'Waiting for the Ingest jobs workflow to start' }).in('id', ids)
  return Response.json({ dispatched: claimed.length })
})
