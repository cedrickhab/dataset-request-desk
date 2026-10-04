import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { Dashboard } from './Dashboard'
import { makeUser, renderWithProviders } from '../test/helpers'
import type { QualityDay, QualitySeries } from '../api/types'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

function stubStaffFetch(
  qualityDays: QualityDay[] = [],
  quality: QualitySeries | null = null,
) {
  const qualityCalls: string[] = []
  vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
    const urlStr = typeof input === 'string' ? input : (input as Request).url
    const url = new URL(urlStr, 'http://localhost')
    let body: unknown
    if (url.pathname.endsWith('/auth/me')) {
      body = makeUser({ role: 'operator', name: 'Olu Operator' })
    } else if (url.pathname.endsWith('/episode-quality')) {
      qualityCalls.push(url.search)
      body =
        quality ??
        {
          start: url.searchParams.get('start'),
          end: url.searchParams.get('end'),
          timezone: 'Africa/Kigali',
          days: qualityDays,
          data_start: qualityDays[0]?.date ?? null,
          total_imported: qualityDays.reduce(
            (sum, day) => {
              return sum + day.good + day.usable + day.bad
            },
            0,
          ),
          semantics: {},
        }
    } else {
      body = { count: url.searchParams.has('status') ? 12 : 60, results: [], next: null, previous: null }
    }
    return Promise.resolve(new Response(JSON.stringify(body)))
  }))
  return qualityCalls
}

it('uses API status totals even when the recent page contains only one status', async () => {
  stubStaffFetch()
  renderWithProviders(<Dashboard />)
  const label = await screen.findByText('Delivered', { selector: '.card small' })
  const card = label.closest('.card') as HTMLElement
  expect(within(card).getByText('12')).toBeInTheDocument()
  const totalCard = screen.getByText('Requests', { exact: true }).closest('.card') as HTMLElement
  expect(within(totalCard).getByText('60')).toBeInTheDocument()
})

it('shows the staff quality chart fed by the episode-quality endpoint', async () => {
  const calls = stubStaffFetch([
    { date: '2026-10-02', good: 3, usable: 1, bad: 0 },
  ])
  renderWithProviders(<Dashboard />)

  expect(await screen.findByRole('heading', { name: 'Episode quality' })).toBeInTheDocument()
  expect(calls.length).toBeGreaterThan(0)
  // The range defaults to 30 days ending today, in query parameters the
  // backend interprets on the Africa/Kigali calendar.
  expect(calls[0]).toContain('start=')
  expect(calls[0]).toContain('end=')
  // The series actually reaches the chart: legend keys and the data table.
  expect(screen.getByRole('heading', { name: 'Episode quality' })).toBeInTheDocument()
  expect(await screen.findByRole('table', { name: 'Daily imported episodes by quality' })).toBeInTheDocument()
})

it('refetches the quality series when the range changes', async () => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-03T22:30:00Z')) // already October 4 in Kigali
  const calls = stubStaffFetch([
    { date: '2026-10-02', good: 3, usable: 1, bad: 0 },
  ])
  renderWithProviders(<Dashboard />)
  await screen.findByRole('heading', { name: 'Episode quality' })
  const initial = calls.length
  expect(calls[0]).toBe('?start=2026-09-05&end=2026-10-04')

  await userEvent.click(screen.getByRole('button', { name: '7 days' }))

  // A new request for the shorter range was made, with a later start date.
  await vi.waitFor(() => {
    expect(calls.length).toBeGreaterThan(initial)
    const searches = new Set(calls)
    expect(searches.size).toBeGreaterThan(1)
  })
  expect(calls.at(-1)).toBe('?start=2026-09-28&end=2026-10-04')
  await vi.waitFor(() => expect(screen.getByRole('button', { name: '90 days' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: '90 days' }))
  await vi.waitFor(() => expect(calls.at(-1)).toBe('?start=2026-07-07&end=2026-10-04'))
})

it('explains absent history and confirmed zero imports without preview counts', async () => {
  stubStaffFetch()
  const { unmount } = renderWithProviders(<Dashboard />)
  expect(await screen.findByText('Import episodes to see daily quality here.')).toBeInTheDocument()
  unmount()
  stubStaffFetch([{ date: '2026-10-02', good: 0, usable: 0, bad: 0 }])
  renderWithProviders(<Dashboard />)
  expect(await screen.findByText('No episodes were imported in this range.')).toBeInTheDocument()
  expect(screen.getByRole('table', { name: 'Daily imported episodes by quality' })).toHaveTextContent('2026-10-02')
})

it('does not request the staff quality series for a client', async () => {
  const qualityCalls: string[] = []
  vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
    const urlStr = typeof input === 'string' ? input : (input as Request).url
    const url = new URL(urlStr, 'http://localhost')
    if (url.pathname.endsWith('/episode-quality')) qualityCalls.push(url.search)
    const body = url.pathname.endsWith('/auth/me') ? makeUser() : { count: 0, results: [], next: null, previous: null }
    return Promise.resolve(new Response(JSON.stringify(body)))
  }))
  renderWithProviders(<Dashboard />)

  await screen.findByRole('heading', { name: 'How your request moves' })
  expect(qualityCalls).toHaveLength(0)
})
