import { chromium } from '@playwright/test'
import { appendFileSync, readFileSync } from 'node:fs'
const [profile, prUrl, list, ...files] = process.argv.slice(2)
const done = () => new Set(readFileSync(list, 'utf8').split('\n').filter(Boolean).map(l => l.split('\t')[0]))
for (let attempt = 1; attempt <= 12; attempt++) {
  const todo = files.filter(f => !done().has(f.split('/').pop()))
  if (!todo.length) { console.log('all uploaded'); process.exit(0) }
  const ctx = await chromium.launchPersistentContext(profile, { channel: 'chrome', headless: true })
  const page = await ctx.newPage()
  let limited = false
  page.on('response', r => { if (r.status() === 429) limited = true })
  await page.goto(prUrl)
  const ta = page.locator('#new_comment_field')
  for (const f of todo) {
    await ta.fill('')
    await page.locator('#fc-new_comment_field').setInputFiles(f)
    try {
      await page.waitForFunction(() => /user-attachments\/assets\/[^"]+"/.test(document.querySelector('#new_comment_field').value), null, { timeout: 30000 })
    } catch { break }
    appendFileSync(list, f.split('/').pop() + '\t' + (await ta.inputValue()).match(/src="([^"]+)"/)[1] + '\n')
    await page.waitForTimeout(2000)
  }
  await ta.fill('')  // never post the comment
  await ctx.close()
  console.log(`attempt ${attempt}: ${done().size} uploaded${limited ? ' (rate limited)' : ''}`)
  if (files.every(f => done().has(f.split('/').pop()))) { console.log('all uploaded'); process.exit(0) }
  await new Promise(r => setTimeout(r, 5 * 60 * 1000))
}
process.exit(1)
