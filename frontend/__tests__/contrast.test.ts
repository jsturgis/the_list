// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { composite, contrast, resolve, themeTokens } from './theme'

// Every text (and meaningful icon) / background pair the theme is used for, with its WCAG AA minimum: 4.5:1 for
// text, 3:1 for icons, borders and placeholders that carry meaning. Translucent backgrounds are painted over the
// surface they sit on, which sits on the page. When a component starts pairing tokens a new way, add the pair here.
const PAIRS: [text: string, background: string, use: string, min: number][] = [
  ['ink', 'page', 'text on the page', 4.5],
  ['ink', 'surface', 'text on rows, panels, the header', 4.5],
  ['ink-soft', 'surface', 'Venue lines, detail values', 4.5],
  ['ink-soft', 'page', 'detail values on the page', 4.5],
  ['ink-muted', 'surface', 'meta text, supports, captions', 4.5],
  ['ink-muted', 'page', 'meta text, the header tagline', 4.5],
  ['ink-muted', 'panel', 'filter labels', 4.5],
  ['ink', 'field', 'text in form fields', 4.5],
  ['ink-faint', 'field', 'placeholders', 3],
  ['ink-faint', 'surface', 'decorative and icon-button icons', 3],
  ['link', 'surface', 'links on rows and panels', 4.5],
  ['link', 'page', 'links on the page', 4.5],
  ['on-accent', 'accent', 'primary button labels', 4.5],
  ['link', 'accent-chip', '"active" tag', 4.5],
  ['accent-soft-ink', 'accent-soft', 'banner text', 4.5],
  ['accent-chip-ink', 'accent-chip', 'tag text ("Local")', 4.5],
  ['ink', 'pick', "Steve's Pick headliner", 4.5],
  ['ink-muted', 'pick', "Steve's Pick supports and meta", 4.5],
  ['ink-soft', 'pick', "Steve's Pick Venue line", 4.5],
  ['pick-line', 'pick', "Steve's Pick star", 3],
  ['on-inverse', 'inverse', 'toast text', 4.5],
  ['inverse-muted', 'inverse', 'toast secondary text', 4.5],
  ['on-inverse', 'strong', 'neutral button label', 4.5],
  ['danger', 'danger-soft', 'Cancelled and Sold out badges', 4.5],
  ['danger', 'surface', 'error messages', 4.5],
  ['warning', 'warning-soft', 'Postponed badge', 4.5],
  ['success', 'success-soft', 'Benefit badge', 4.5],
  ['info', 'info-soft', 'Matinee badge', 4.5],
  ['hot', 'hot-soft', 'Will Sell Out badge', 4.5],
  ['ink-soft', 'muted', 'neutral flags and genre tags', 4.5],
]

const TRANSLUCENT_ON_SURFACE = new Set(['pick', 'accent-soft', 'accent-chip', 'danger-soft', 'warning-soft', 'success-soft', 'info-soft', 'hot-soft'])

function ratio(mode: 'light' | 'dark', text: string, background: string): number {
  const t = themeTokens[mode]
  const value = (name: string) => {
    const v = t.get(name)
    if (!v) throw new Error(`No ${mode} token ${name}`)
    return resolve(v)
  }
  const under = [value('page'), ...(TRANSLUCENT_ON_SURFACE.has(background) ? [value('surface')] : [])]
  const bg = composite(...under, value(background))
  return contrast(composite(bg, value(text)), bg)
}

describe('theme colours', () => {
  it('resolve like a browser does', () => {
    // Spot checks against Chromium's rendering of the same values.
    expect(resolve('#1ed760').slice(0, 3).map(v => Math.round(v * 255))).toEqual([30, 215, 96])
    expect(resolve('--theme(--color-red-700 inline)').slice(0, 3).map(v => Math.round(v * 255))).toEqual([193, 0, 7])
    expect(contrast(resolve('#121212'), resolve('#ffffff'))).toBeCloseTo(18.73, 1)
  })

  for (const mode of ['light', 'dark'] as const) {
    it(`meet WCAG AA for every pair in ${mode} mode`, () => {
      const failures = PAIRS.flatMap(([text, background, use, min]) => {
        const r = ratio(mode, text, background)
        return r < min ? [`${text} on ${background} (${use}): ${r.toFixed(2)}:1, needs ${min}:1`] : []
      })
      expect(failures).toEqual([])
    })
  }
})
