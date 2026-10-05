import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { shiftDay, todayInBusinessZone } from './format'
import { EpisodeQualityCard } from './EpisodeQualityCard'

 afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

function stubQualitySeries() {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
    const inputUrl = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(inputUrl, 'http://localhost')
    calls.push(url.href)
    const start = url.searchParams.get('start') ?? '2026-10-01'
    const end = url.searchParams.get('end') ?? start
    return Promise.resolve(
      new Response(JSON.stringify({
        start,
        end,
        timezone: 'Africa/Kigali',
        days: [{ date: start, good: 4, usable: 2, bad: 1 }],
        data_start: start,
        total_imported: 7,
        semantics: {},
      })),
    )
  }))
  return calls
}

it('fetches real daily data for this week, this month, and custom ranges', async () => {
  const user = userEvent.setup()
  const calls = stubQualitySeries()
  render(<EpisodeQualityCard />)

  const chart = await screen.findByRole('img', { name: /Daily Good, Usable, and Bad episode counts/ })
  expect(chart.querySelectorAll('.quality-column')).toHaveLength(3)
  expect(chart.querySelectorAll('.quality-grid-line')).toHaveLength(4)
  expect(chart.querySelector('.quality-axis-line')).not.toBeNull()
  const today = todayInBusinessZone()
  const weekday = new Date(`${today}T00:00:00Z`).getUTCDay()
  const weekStart = shiftDay(today, -((weekday + 6) % 7))
  expect(new URL(calls[0]!).searchParams.get('start')).toBe(weekStart)
  expect(new URL(calls[0]!).searchParams.get('end')).toBe(today)

  await user.click(screen.getByRole('button', { name: 'This month' }))
  await waitFor(() => expect(calls).toHaveLength(2))
  expect(new URL(calls[1]!).searchParams.get('start')).toBe(`${today.slice(0, 7)}-01`)
  expect(new URL(calls[1]!).searchParams.get('end')).toBe(today)

  await user.click(screen.getByRole('button', { name: 'Custom' }))
  const customStart = shiftDay(today, -10)
  const customEnd = shiftDay(today, -2)
  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: customStart } })
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: customEnd } })
  await user.click(screen.getByRole('button', { name: 'Apply dates' }))
  await waitFor(() => expect(calls).toHaveLength(3))
  expect(new URL(calls[2]!).searchParams.get('start')).toBe(customStart)
  expect(new URL(calls[2]!).searchParams.get('end')).toBe(customEnd)
})

it('rejects custom ranges longer than the API limit', async () => {
  const user = userEvent.setup()
  const calls = stubQualitySeries()
  render(<EpisodeQualityCard />)

  await screen.findByRole('img', { name: /Daily Good, Usable, and Bad episode counts/ })
  await user.click(screen.getByRole('button', { name: 'Custom' }))
  const today = todayInBusinessZone()
  fireEvent.change(screen.getByLabelText('Start date'), {
    target: { value: shiftDay(today, -366) },
  })
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: today } })
  await user.click(screen.getByRole('button', { name: 'Apply dates' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('at most 366 days')
  expect(calls).toHaveLength(1)
})
