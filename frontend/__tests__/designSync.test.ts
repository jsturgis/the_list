// @vitest-environment node
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { rawTokens } from './theme'

// DESIGN.md (repository root) describes every colour token of the theme in frontend/src/styles/globals.css.
// This keeps the two from drifting: the same token names, with the same light and dark values.

const design = readFileSync(join(process.cwd(), '..', 'DESIGN.md'), 'utf8')

/** `--theme(--color-red-600 inline)` is written `red-600` in DESIGN.md. */
const normalise = (value: string) => value.trim().replace(/--theme\(--color-([a-z0-9-]+) inline\)/g, '$1')
const normalised = (tokens: Map<string, string>) => new Map([...tokens].map(([name, value]) => [name, normalise(value)]))

const light = normalised(rawTokens.light)
const dark = normalised(rawTokens.dark)

const palette = design.slice(design.indexOf('## 2. Colour Palette'), design.indexOf('## 3.'))
const documented = new Map(
  [...palette.matchAll(/^\| `([a-z-]+)` \| [^|]* \| `([^`]+)` \| `([^`]+)` \|$/gm)].map(([, name, l, d]) => [name, { light: l, dark: d }]),
)

describe('DESIGN.md and the theme', () => {
  it('reads both', () => {
    expect(light.size).toBeGreaterThan(30)
    expect(dark.size).toBeGreaterThan(30)
    expect(documented.size).toBeGreaterThan(30)
  })

  it('describes every token the theme defines, and no others', () => {
    const themed = [...new Set([...light.keys(), ...dark.keys()])].sort()
    const missingFromDesign = themed.filter(name => !documented.has(name))
    const missingFromTheme = [...documented.keys()].filter(name => !light.has(name) || !dark.has(name))
    expect({ missingFromDesign, missingFromTheme }).toEqual({ missingFromDesign: [], missingFromTheme: [] })
  })

  it('gives each token the same light and dark values as the theme', () => {
    const mismatches = [...documented].flatMap(([name, values]) => [
      ...(light.has(name) && light.get(name) !== values.light ? [`${name} (light): DESIGN.md ${values.light}, theme ${light.get(name)}`] : []),
      ...(dark.has(name) && dark.get(name) !== values.dark ? [`${name} (dark): DESIGN.md ${values.dark}, theme ${dark.get(name)}`] : []),
    ])
    expect(mismatches).toEqual([])
  })
})
