import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { graphql } from 'msw/graphql'
import { HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import type { ComponentProps } from 'react'
import SimilarBands from '@/components/SimilarBands'
import { InModalContext } from '@/components/Modal'
import { makeBand } from './fixtures'

// Expose Link's `replace` prop so we can assert on history behaviour.
vi.mock('next/link', () => ({
  default: ({ replace, ...props }: ComponentProps<'a'> & { replace?: boolean }) => (
    <a data-replace={replace ? 'true' : 'false'} {...props} />
  ),
}))
vi.mock('next/navigation', () => ({ useRouter: () => ({ back: vi.fn() }) }))

const api = graphql.link('http://localhost:8000/graphql')
const server = setupServer(
  api.query('GetSimilarBands', () =>
    HttpResponse.json({ data: { similarBands: [makeBand({ id: 7, name: 'Alcest' })] } }),
  ),
)
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('SimilarBands history behaviour', () => {
  it('pushes a new history entry on the full Band page', async () => {
    render(<SimilarBands bandId={1} />)
    expect(await screen.findByRole('link', { name: /Alcest/ })).toHaveAttribute('data-replace', 'false')
  })

  it('replaces the history entry inside the modal', async () => {
    render(
      <InModalContext.Provider value={true}>
        <SimilarBands bandId={1} />
      </InModalContext.Provider>,
    )
    expect(await screen.findByRole('link', { name: /Alcest/ })).toHaveAttribute('data-replace', 'true')
  })
})
