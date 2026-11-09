/**
 * Draws the docs pages' diagrams: each ```mermaid block in a guide, which guideHtml (lib/docs) turned into a
 * `[data-diagram]` region holding its source. Mermaid is large, so the page loads this only when it has a diagram,
 * and this loads Mermaid only then. The diagrams take the theme's colour tokens (DESIGN.md), read from the page, and
 * are drawn again when the system switches between light and dark. If Mermaid fails, the source stays on the page.
 */
import type { MermaidConfig } from 'mermaid'

/** A colour token's current value, by name (`ink` for `--ink`). */
type Token = (name: string) => string

/** Mermaid's theme variables (its `base` theme) from the site's colour tokens. */
export function themeVariables(token: Token): NonNullable<MermaidConfig['themeVariables']> {
  const surface = token('surface')
  const page = token('page')
  const muted = token('muted')
  const ink = token('ink')
  const inkSoft = token('ink-soft')
  const inkMuted = token('ink-muted')
  const line = token('line')
  const lineStrong = token('line-strong')
  return {
    fontFamily: "'Figtree Variable', ui-sans-serif, system-ui, sans-serif",
    fontSize: '15px',
    background: surface,
    textColor: ink,
    // Boxes: muted chips with ink text and a strong border; groups (subgraphs) a step down, on the page colour.
    primaryColor: muted,
    primaryTextColor: ink,
    primaryBorderColor: lineStrong,
    mainBkg: muted,
    nodeBorder: lineStrong,
    nodeTextColor: ink,
    secondaryColor: page,
    secondaryTextColor: ink,
    secondaryBorderColor: lineStrong,
    tertiaryColor: page,
    tertiaryTextColor: ink,
    tertiaryBorderColor: line,
    clusterBkg: page,
    clusterBorder: lineStrong,
    titleColor: inkSoft,
    // Arrows and their labels.
    lineColor: inkMuted,
    edgeLabelBackground: surface,
    // Sequence diagrams.
    actorBkg: muted,
    actorBorder: lineStrong,
    actorTextColor: ink,
    actorLineColor: lineStrong,
    signalColor: inkMuted,
    signalTextColor: ink,
    labelBoxBkgColor: muted,
    labelBoxBorderColor: lineStrong,
    labelTextColor: ink,
    loopTextColor: ink,
    noteBkgColor: token('accent-soft'),
    noteBorderColor: token('accent-soft-line'),
    noteTextColor: token('accent-soft-ink'),
    activationBkgColor: page,
    activationBorderColor: lineStrong,
    // Entity-relationship diagrams: the attribute rows alternate.
    rowOdd: surface,
    rowEven: page,
  }
}

/** The smallest a diagram is drawn, as a share of its own size: below it, its panel scrolls sideways instead. */
export const MIN_SCALE = 0.8

/**
 * Size a drawn diagram: at most its own size, shrunk to fit the column down to MIN_SCALE, so its text stays
 * readable. The panel scrolls sideways past that (phones).
 */
function fit(out: HTMLElement): void {
  const svg = out.querySelector('svg')
  const width = svg?.viewBox.baseVal?.width
  if (!svg || !width) return
  svg.removeAttribute('width')
  svg.removeAttribute('height')
  svg.style.width = '100%'
  svg.style.maxWidth = `${width}px`
  out.style.setProperty('--diagram-min', `${Math.round(width * MIN_SCALE)}px`)
}

/** Draw every diagram on the page, and again whenever the colour scheme changes. */
export async function drawDiagrams(root: ParentNode = document): Promise<void> {
  const regions = [...root.querySelectorAll<HTMLElement>('[data-diagram]')]
  if (!regions.length) return
  const { default: mermaid } = await import('mermaid')
  const dark = window.matchMedia('(prefers-color-scheme: dark)')
  let drawing = Promise.resolve()

  const draw = async () => {
    // Mermaid measures the labels as it lays them out, so Figtree must have loaded.
    await document.fonts.ready
    const style = getComputedStyle(document.documentElement)
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      darkMode: dark.matches,
      themeVariables: themeVariables(name => style.getPropertyValue(`--${name}`).trim()),
      // Drawn at their own size: the panel scrolls sideways rather than shrinking the text to fit a phone.
      flowchart: { useMaxWidth: false, padding: 12 },
      sequence: { useMaxWidth: false, width: 100, actorMargin: 24, diagramMarginX: 8, diagramMarginY: 8 },
      er: { useMaxWidth: false },
    })
    for (const [i, region] of regions.entries()) {
      const source = region.querySelector('pre')
      if (!source) continue
      try {
        const { svg } = await mermaid.render(`diagram-${i}`, source.textContent ?? '')
        let out = region.querySelector<HTMLElement>('.docs-diagram-svg')
        if (!out) {
          out = document.createElement('div')
          out.className = 'docs-diagram-svg'
          region.append(out)
        }
        out.innerHTML = svg
        fit(out)
        source.hidden = true
      } catch (error) {
        console.error('Could not draw a diagram; showing its source instead.', error)
      }
    }
  }

  // One drawing at a time: Mermaid's render isn't safe to run twice at once.
  const redraw = () => (drawing = drawing.then(draw))
  dark.addEventListener('change', () => void redraw())
  await redraw()
}
