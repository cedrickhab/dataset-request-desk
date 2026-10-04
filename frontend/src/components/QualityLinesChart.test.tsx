import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it } from 'vitest'

import { QualityLinesChart } from './QualityLinesChart'

const days = [
  { date: '2026-10-01', good: 3, usable: 2, bad: 1 },
  { date: '2026-10-02', good: 0, usable: 0, bad: 0 },
  { date: '2026-10-03', good: 1, usable: 4, bad: 2 },
]

it('shares a date and all three counts across keyboard, pointer and touch selection', () => {
  const { container } = render(<QualityLinesChart days={days} />)
  const chart = screen.getByRole('group')
  const summary = container.querySelector('[aria-live]')!
  fireEvent.focus(chart)
  expect(summary).toHaveTextContent('Good 1, Usable 4, Bad 2, Total 7')
  fireEvent.keyDown(chart, { key: 'Home' })
  expect(summary).toHaveTextContent('Good 3, Usable 2, Bad 1, Total 6')
  fireEvent.keyDown(chart, { key: 'ArrowRight' })
  expect(summary).toHaveTextContent('Good 0, Usable 0, Bad 0, Total 0')
  fireEvent.keyDown(chart, { key: 'End' })
  fireEvent.keyDown(chart, { key: 'ArrowLeft' })
  expect(summary).toHaveTextContent('Good 0, Usable 0, Bad 0, Total 0')
  const svg = container.querySelector('svg')!
  fireEvent.pointerMove(svg, { clientX: 40, pointerType: 'mouse' })
  expect(summary).toHaveTextContent('Good 3, Usable 2, Bad 1, Total 6')
  fireEvent.pointerDown(svg, { clientX: 546, pointerType: 'touch' })
  fireEvent.pointerLeave(svg, { pointerType: 'touch' })
  expect(summary).toHaveTextContent('Good 1, Usable 4, Bad 2, Total 7')
  expect(container.querySelectorAll('.qtooltip')).toHaveLength(1)
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(4)
  fireEvent.keyDown(chart, { key: 'Escape' })
  expect(container.querySelector('.qtooltip')).toBeNull()
  fireEvent.focus(chart)
  fireEvent.blur(chart)
  expect(container.querySelector('.qtooltip')).toBeNull()
})

it('renders a single day as three points without inventing a curve', () => {
  const { container } = render(<QualityLinesChart days={[days[0]!]} />)
  expect(container.querySelectorAll('svg path')).toHaveLength(0)
  expect(container.querySelectorAll('svg circle')).toHaveLength(3)
  expect(screen.getByRole('table')).toHaveTextContent('2026-10-01')
})

it('keeps zero series finite and labels small counts without duplicate rounded ticks', () => {
  const { container, rerender } = render(<QualityLinesChart days={days.map(day => ({ ...day, good: 0, usable: 0, bad: 0 }))} />)
  for (const path of container.querySelectorAll('svg path')) {
    expect(path.getAttribute('d')).not.toMatch(/NaN|Infinity/)
  }
  rerender(<QualityLinesChart days={[{ date: '2026-10-01', good: 1, usable: 0, bad: 0 }]} />)
  const ticks = [...container.querySelectorAll('svg g text')].map(node => node.textContent)
  expect(ticks).toEqual(['0', '1'])
})

it('handles no history without inventing any dates', () => {
  const { container } = render(<QualityLinesChart days={[]} />)
  fireEvent.focus(screen.getByRole('group'))
  fireEvent.keyDown(screen.getByRole('group'), { key: 'ArrowRight' })
  expect(screen.getByText('No import data.')).toBeInTheDocument()
  expect(container.querySelector('.qtooltip')).toBeNull()
  expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(1)
})
