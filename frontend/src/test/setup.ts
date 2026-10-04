import '@testing-library/jest-dom/vitest'

// jsdom has no ResizeObserver; the chart and the login artwork measure their
// containers with one. A stub keeps components mounted in tests rendering
// with their fallback dimensions instead of crashing.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver
