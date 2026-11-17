// A signed-in admin on the Admin page, for the e2e checks and the screenshots: a session in local storage, and
// Supabase's REST API answered locally with a job at each stage. `host` is the build's placeholder Supabase host
// (e2e.invalid, screenshots.invalid). Realtime can't connect, so the page falls back to polling these.

const job = (changes) => ({
  id: 'job-1', provider: 'ticketweb', url: 'https://www.ticketweb.com/event/neon-harbor-the-chapel-tickets/14446334',
  screenshot_path: null, status: 'queued', phase: 'queued', detail: null, message: null, extracted: null, show_id: null,
  workflow_run_url: null, attempts: 1, created_at: '2026-10-01T18:50:00Z', updated_at: '2026-10-01T18:58:00Z',
  ...changes,
})

export const ADMIN_JOBS = [
  job({ id: 'job-4', status: 'running', phase: 'bands', detail: 'Looking up Band 2 of 3: Static Bloom',
        workflow_run_url: 'https://github.com/jsturgis/the_list/actions/runs/1', created_at: '2026-10-01T18:55:00Z' }),
  job({ id: 'job-3', provider: 'screenshot', url: null, screenshot_path: 'user-1/a.png', status: 'failed',
        phase: 'reading_screenshot', message: 'The Fillmore is in Portland, not a Bay Area city we know',
        extracted: { performers: ['Redwood Sirens'], venue: 'The Fillmore', city: 'Portland', month: 10, day: 9, year: null },
        created_at: '2026-10-01T18:40:00Z' }),
  job({ id: 'job-2', status: 'added', phase: 'deploying', detail: 'https://github.com/jsturgis/the_list/actions/runs/2',
        message: 'Added Neon Harbor at The Chapel, San Francisco on Sat Oct 3, 2026', show_id: 1,
        created_at: '2026-10-01T18:30:00Z' }),
  job({ id: 'job-1', status: 'live', phase: 'live', message: 'Added Neon Harbor at 924 Gilman Street, Berkeley on Sat Oct 3, 2026',
        show_id: 1, workflow_run_url: 'https://github.com/jsturgis/the_list/actions/runs/0', created_at: '2026-10-01T17:00:00Z' }),
]

export async function signedInAsAdmin(page, host) {
  const ref = host.split('.')[0]
  await page.addInitScript(key => {
    localStorage.setItem(key, JSON.stringify({
      access_token: 'e2e', token_type: 'bearer', expires_in: 3600, expires_at: 4102444800, refresh_token: 'e2e',
      user: { id: 'user-1', email: 'admin@example.com', aud: 'authenticated', role: 'authenticated',
              app_metadata: { permissions: ['admin'] }, user_metadata: {} },
    }))
  }, `sb-${ref}-auth-token`)
  await page.route(`https://${host}/rest/v1/**`, route =>
    new URL(route.request().url()).pathname.endsWith('/ingest_jobs')
      ? route.fulfill({ json: ADMIN_JOBS })
      : route.fulfill({ status: 404, json: {} }))
}
