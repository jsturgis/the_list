import type { Locator, Page } from '@playwright/test'
import { expect, test } from './fixtures'

// Keyboard-only use of the site (#70): only Tab, Shift+Tab, Enter, Escape and typing, as a keyboard user would.
// The e2e build has placeholder Supabase settings (https://e2e.invalid); the routes below stand in for Supabase.

/** Press Tab until `target` has focus (at most `max` times). */
async function tabTo(page: Page, target: Locator, max = 60) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab')
    if (await target.evaluate(el => el === document.activeElement).catch(() => false)) return
  }
  throw new Error(`Tab never reached ${target}`)
}

const focused = (page: Page) => page.locator(':focus')

/** A signed-in visitor with two alerts: a session in local storage, and Supabase's REST API answered locally. */
async function signedInWithAlerts(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('sb-e2e-auth-token', JSON.stringify({
      access_token: 'e2e', token_type: 'bearer', expires_in: 3600, expires_at: 4102444800, refresh_token: 'e2e',
      user: { id: 'user-1', email: 'fan@example.com', aud: 'authenticated', role: 'authenticated', app_metadata: {}, user_metadata: {} },
    }))
  })
  let alerts = [
    { id: 'a1', name: 'East Bay punk', query: 'genre=punk&region=east_bay', created_at: '2026-09-20T00:00:00Z' },
    { id: 'a2', name: 'Free', query: 'free=1', created_at: '2026-09-21T00:00:00Z' },
  ]
  await page.route('https://e2e.invalid/rest/v1/**', async route => {
    const url = new URL(route.request().url())
    const single = (route.request().headers()['accept'] ?? '').includes('vnd.pgrst.object')
    if (url.pathname.endsWith('/saved_filters') && route.request().method() === 'DELETE') {
      const id = url.searchParams.get('id')?.replace('eq.', '')
      alerts = alerts.filter(a => a.id !== id)
      return route.fulfill({ status: 204 })
    }
    if (url.pathname.endsWith('/saved_filters')) return route.fulfill({ json: alerts })
    if (url.pathname.endsWith('/alert_subscriptions')) return route.fulfill({ json: single ? { enabled: true } : [{ enabled: true }] })
    return route.fulfill({ status: 404, json: {} })
  })
}

test('the first Tab reaches "Skip to content", which moves focus to the page content', async ({ page }) => {
  await page.goto('shows/102/')
  await page.keyboard.press('Tab')
  const skip = page.getByRole('link', { name: 'Skip to content' })
  await expect(skip).toBeFocused()
  await expect(skip).toBeInViewport()
  await page.keyboard.press('Enter')
  await expect(page.locator('main')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(focused(page)).toHaveText(/Back/)  // the first thing in the content, not the header
})

test('keyboard focus is visible on fields, buttons, links and Show rows', async ({ page }) => {
  await page.goto('./?region=east_bay')
  for (const target of [page.getByLabel('Search'), page.getByRole('button', { name: /save search/i }), page.getByRole('link', { name: 'Your alerts' })]) {
    await page.locator('body').click({ position: { x: 1, y: 1 } })
    await tabTo(page, target)
    await expect(target).toHaveCSS('outline-style', 'solid')
    await expect(target).toHaveCSS('outline-color', 'rgb(17, 122, 55)')  // focus-ring, light mode
  }
  const showLink = page.locator('main [data-show-link]').first()
  await tabTo(page, showLink)
  const row = page.locator('main [data-recommended], main [data-show-link]').first().locator('xpath=ancestor-or-self::div[contains(@class, "relative")][1]')
  await expect(row).not.toHaveCSS('box-shadow', 'none')  // the row's focus ring
})

test('Save search panel: focus moves in, Escape returns it, and Tab past the end closes it', async ({ page }) => {
  await page.goto('./?region=east_bay')
  const button = page.getByRole('button', { name: /save search/i })
  await tabTo(page, button)
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Name')).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByLabel('Name')).toHaveCount(0)
  await expect(button).toBeFocused()

  await page.keyboard.press('Enter')
  await tabTo(page, page.getByRole('button', { name: /sign-in link/i }), 5)
  await page.keyboard.press('Tab')  // past the form's last control
  await expect(page.getByLabel('Name')).toHaveCount(0)
  await expect(focused(page)).not.toHaveAttribute('id', 'save-filter-name')
})

test('keyboard only: set up an alert', async ({ page }) => {
  let requested = ''
  await page.route('https://e2e.invalid/auth/v1/otp**', async route => {
    requested = route.request().postDataJSON().email
    await route.fulfill({ json: {} })
  })
  await page.goto('./')
  await tabTo(page, page.getByLabel('Search'))
  await page.keyboard.type('gilman')
  await expect(page).toHaveURL(/q=gilman/)
  const button = page.getByRole('button', { name: /save search/i })
  await tabTo(page, button, 10)  // after the filters, at the end of the filter bar
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Name')).toHaveValue('"gilman"')
  await page.keyboard.press('Tab')
  await page.keyboard.type('fan@example.com')
  await page.keyboard.press('Enter')

  await expect(page.getByText(/check your email for a sign-in link/i)).toBeVisible()
  expect(requested).toBe('fan@example.com')
  await expect(button).toBeFocused()  // not lost when the form went away
  await tabTo(page, page.getByRole('button', { name: 'Dismiss' }), 5)
  await page.keyboard.press('Enter')
  await expect(page.getByText(/check your email/i)).toHaveCount(0)
  await expect(button).toBeFocused()
})

test('keyboard only: open a Show, then a Band, then go back', async ({ page }) => {
  await page.goto('./')
  await tabTo(page, page.locator('main [data-show-link]').first())
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/shows\/102\/$/)

  await tabTo(page, page.getByRole('main').getByRole('link', { name: 'Static Bloom' }))
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/bands\/3\/$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Static Bloom' })).toBeVisible()

  await tabTo(page, page.getByRole('link', { name: 'Back' }))
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/shows\/102\/$/)
})

test('keyboard only: delete an alert', async ({ page }) => {
  await signedInWithAlerts(page)
  await page.goto('alerts/')
  await expect(page.getByText('2 of 20 alerts')).toBeVisible()

  await tabTo(page, page.getByRole('button', { name: 'Delete East Bay punk' }))
  await page.keyboard.press('Enter')
  await expect(page.getByText(/Deleted “East Bay punk”/)).toBeVisible()
  await expect(page.getByText('1 of 20 alerts')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Free' })).toBeFocused()  // the next alert, not the top of the page
})
