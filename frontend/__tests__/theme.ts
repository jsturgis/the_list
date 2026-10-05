/**
 * Test helpers for the colour theme in src/styles/globals.css: its light and dark token values, resolved to sRGB
 * colours (Tailwind palette references, oklch values and `color-mix(…, transparent)` included), and WCAG contrast.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export const themeCss = readFileSync(join(process.cwd(), 'src', 'styles', 'globals.css'), 'utf8')
const tailwindTheme = readFileSync(join(process.cwd(), 'node_modules', 'tailwindcss', 'theme.css'), 'utf8')

function tokens(block: string): Map<string, string> {
  return new Map([...block.matchAll(/--([a-z-]+):\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()]))
}

const darkStart = themeCss.indexOf('@media (prefers-color-scheme: dark)')
/** The theme's tokens as written, by mode. Dark mode only lists what it changes; `themeTokens.dark` merges in light. */
export const rawTokens = {
  light: tokens(themeCss.slice(themeCss.indexOf(':root {'), darkStart)),
  dark: tokens(themeCss.slice(darkStart, themeCss.indexOf('@theme inline'))),
}
export const themeTokens = {
  light: rawTokens.light,
  dark: new Map([...rawTokens.light, ...rawTokens.dark]),
}

const palette = new Map([...tailwindTheme.matchAll(/--color-([a-z0-9-]+):\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()]))

/** An sRGB colour, channels 0–1, with alpha. */
export type Rgba = [number, number, number, number]

const clamp = (v: number) => Math.min(1, Math.max(0, v))
const encode = (v: number) => (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055)

/** OKLCH (L 0–1, C, H in degrees) to sRGB, clipped to the sRGB gamut as browsers do for display. */
function oklch(l: number, c: number, h: number): Rgba {
  const a = c * Math.cos((h * Math.PI) / 180)
  const b = c * Math.sin((h * Math.PI) / 180)
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3
  const r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
  const g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
  const bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_
  return [clamp(encode(r)), clamp(encode(g)), clamp(encode(bl)), 1]
}

/** Resolve a token value (hex, Tailwind palette reference, oklch, or `color-mix(in oklab, X P%, transparent)`). */
export function resolve(value: string): Rgba {
  const v = value.trim()
  let m
  if ((m = v.match(/^--theme\(--color-([a-z0-9-]+) inline\)$/))) {
    const p = palette.get(m[1])
    if (!p) throw new Error(`Unknown Tailwind colour ${m[1]}`)
    return resolve(p)
  }
  if ((m = v.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i))) {
    const hex = m[1].length === 3 ? [...m[1]].map(c => c + c).join('') : m[1]
    return [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).concat(1) as Rgba
  }
  if ((m = v.match(/^oklch\(([\d.]+)%\s+([\d.]+)\s+([\d.]+)\)$/))) return oklch(Number(m[1]) / 100, Number(m[2]), Number(m[3]))
  if ((m = v.match(/^color-mix\(in oklab,\s*(.+)\s+([\d.]+)%,\s*transparent\)$/))) {
    // Mixing with transparent keeps the colour and scales its alpha (premultiplied interpolation).
    const [r, g, b, a] = resolve(m[1])
    return [r, g, b, a * (Number(m[2]) / 100)]
  }
  throw new Error(`Can't resolve colour ${v}`)
}

/** Paint colours over each other, back to front (alpha compositing in sRGB, as browsers do). */
export function composite(...layers: Rgba[]): Rgba {
  return layers.reduce<Rgba>((under, [r, g, b, a]) => [
    r * a + under[0] * (1 - a), g * a + under[1] * (1 - a), b * a + under[2] * (1 - a), 1,
  ], [1, 1, 1, 1])
}

function luminance([r, g, b]: Rgba): number {
  const lin = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

/** WCAG contrast ratio of two opaque colours. */
export function contrast(a: Rgba, b: Rgba): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}
