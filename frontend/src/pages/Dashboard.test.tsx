import { screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { Dashboard } from './Dashboard'
import { makeRequest, makeUser, renderWithProviders } from '../test/helpers'

afterEach(() => vi.unstubAllGlobals())

it('uses API status totals even when the recent page contains only one status', async () => {
  vi.stubGlobal('fetch', vi.fn((input: string) => {
    const url = new URL(input, 'http://localhost')
    const body = url.pathname.endsWith('/auth/me') ? makeUser()
      : { count: url.searchParams.has('status') ? 12 : 60,
        results: [makeRequest({ status: 'submitted' })], next: null, previous: null }
    return Promise.resolve(new Response(JSON.stringify(body)))
  }))
  renderWithProviders(<Dashboard />)
  const label = await screen.findByText('Awaiting review')
  expect(within(label.closest('.card') as HTMLElement).getByText('12')).toBeInTheDocument()
  const total = screen.getByText('Total requests')
  expect(within(total.closest('.card') as HTMLElement).getByText('60')).toBeInTheDocument()
})
