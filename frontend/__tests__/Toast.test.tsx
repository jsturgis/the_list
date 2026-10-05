import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Toast, { TOAST_MS } from '@/components/Toast'

describe('Toast', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('is announced politely and closes itself after a few seconds', () => {
    const onDismiss = vi.fn()
    render(<Toast onDismiss={onDismiss}>Saved.</Toast>)
    expect(screen.getByRole('status')).toHaveTextContent('Saved.')

    act(() => { vi.advanceTimersByTime(TOAST_MS - 1) })
    expect(onDismiss).not.toHaveBeenCalled()
    act(() => { vi.advanceTimersByTime(1) })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('stays while keyboard focus is on it, so its controls can be reached', () => {
    const onDismiss = vi.fn()
    render(<Toast onDismiss={onDismiss}>Saved.</Toast>)
    fireEvent.focus(screen.getByRole('button', { name: 'Dismiss' }))
    act(() => { vi.advanceTimersByTime(TOAST_MS * 3) })
    expect(onDismiss).not.toHaveBeenCalled()

    fireEvent.blur(screen.getByRole('button', { name: 'Dismiss' }), { relatedTarget: document.body })
    act(() => { vi.advanceTimersByTime(TOAST_MS) })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('stays while the pointer is on it', () => {
    const onDismiss = vi.fn()
    render(<Toast onDismiss={onDismiss}>Saved.</Toast>)
    fireEvent.mouseEnter(screen.getByRole('status'))
    act(() => { vi.advanceTimersByTime(TOAST_MS * 3) })
    expect(onDismiss).not.toHaveBeenCalled()
    fireEvent.mouseLeave(screen.getByRole('status'))
    act(() => { vi.advanceTimersByTime(TOAST_MS) })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
