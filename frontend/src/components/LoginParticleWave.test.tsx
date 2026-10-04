import { act, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { LoginParticleWave } from './LoginParticleWave'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('sizes the drawing to its own CSS box, caps DPR and disconnects on unmount', () => {
  const context = {
    setTransform: vi.fn(), clearRect: vi.fn(), fillRect: vi.fn(), beginPath: vi.fn(),
    arc: vi.fn(), fill: vi.fn(), save: vi.fn(), restore: vi.fn(),
    createRadialGradient: () => ({ addColorStop: vi.fn() }),
  }
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as unknown as CanvasRenderingContext2D)
  const rect = vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect')
    .mockReturnValue({ width: 600, height: 300 } as DOMRect)
  vi.stubGlobal('devicePixelRatio', 3)
  let resize = () => {}
  const observe = vi.fn()
  const disconnect = vi.fn()
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { resize = callback }
    observe = observe
    disconnect = disconnect
  })
  const { container, unmount } = render(<LoginParticleWave />)
  const canvas = container.querySelector('canvas')!
  expect(observe).toHaveBeenCalledWith(canvas)
  expect(canvas.width).toBe(1200)
  expect(canvas.height).toBe(600)
  expect(context.setTransform).toHaveBeenCalledWith(2, 0, 0, 2, 0, 0)
  rect.mockReturnValue({ width: 320, height: 150 } as DOMRect)
  act(() => resize())
  expect(canvas.width).toBe(640)
  expect(canvas.height).toBe(300)
  unmount()
  expect(disconnect).toHaveBeenCalledOnce()
})
