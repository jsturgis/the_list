import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import Modal from '@/components/Modal'

const back = vi.fn()  // the onClose handler

// jsdom doesn't implement <dialog> methods
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
})

beforeEach(() => back.mockClear())

describe('Modal', () => {
  it('opens and renders children', () => {
    render(<Modal onClose={back}><p>Band content</p></Modal>)
    expect(screen.getByRole('dialog')).toHaveAttribute('open')
    expect(screen.getByText('Band content')).toBeInTheDocument()
  })

  it('calls onClose when the close button is clicked', () => {
    render(<Modal onClose={back}><p>Band content</p></Modal>)
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(back).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when the dialog closes (e.g. Esc)', () => {
    render(<Modal onClose={back}><p>Band content</p></Modal>)
    fireEvent(screen.getByRole('dialog'), new Event('close'))
    expect(back).toHaveBeenCalledTimes(1)
  })

  it('calls onClose on backdrop click but not on content click', () => {
    render(<Modal onClose={back}><p>Band content</p></Modal>)
    fireEvent.click(screen.getByText('Band content'))
    expect(back).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('dialog'))
    expect(back).toHaveBeenCalledTimes(1)
  })
})
