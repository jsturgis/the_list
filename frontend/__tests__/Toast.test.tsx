import { act, render, screen } from '@testing-library/react'
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
})
