import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/AuthContext'
import { makeRequest, makeUser, renderWithProviders } from '../test/helpers'
import { Shell } from '../components/Shell'
import { Dashboard } from './Dashboard'
import { RequestDetail } from './RequestDetail'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

function stubStaffFetch(
  totals: {
    totalRequests?: number
    totalEpisodes?: number
    availableEpisodes?: number
    goodEpisodes?: number
    usableEpisodes?: number
    badEpisodes?: number
    requestStatusCounts?: Record<string, number>
  } = {},
) {
  const episodesCalls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string | URL | Request) => {
      const urlStr = typeof input === 'string' ? input : (input as Request).url
      const url = new URL(urlStr, 'http://localhost')

      if (url.pathname.endsWith('/auth/me')) {
        return Promise.resolve(new Response(JSON.stringify(makeUser({ role: 'operator', name: 'Olu Operator' }))))
      }

      if (url.pathname.endsWith('/episode-quality')) {
        const start = url.searchParams.get('start') ?? '2026-10-01'
        const end = url.searchParams.get('end') ?? start
        const hasHistory = totals.totalEpisodes !== 0
        return Promise.resolve(
          new Response(JSON.stringify({
            start,
            end,
            timezone: 'Africa/Kigali',
            days: hasHistory ? [{ date: start, good: 10, usable: 6, bad: 4 }] : [],
            data_start: hasHistory ? start : null,
            total_imported: hasHistory ? 20 : 0,
            semantics: {},
          })),
        )
      }

      if (url.pathname.endsWith('/requests')) {
        const status = url.searchParams.get('status')
        const count = status
          ? totals.requestStatusCounts?.[status] ?? 12
          : totals.totalRequests ?? 60
        return Promise.resolve(
          new Response(
            JSON.stringify({ count, results: [], next: null, previous: null }),
          ),
        )
      }

      if (url.pathname.endsWith('/episodes')) {
        episodesCalls.push(url.search)
        const quality = url.searchParams.get('quality')
        const available = url.searchParams.has('available')

        if (available) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ count: totals.availableEpisodes ?? 12, results: [], next: null, previous: null }),
            ),
          )
        }
        if (quality === 'good') {
          return Promise.resolve(
            new Response(
              JSON.stringify({ count: totals.goodEpisodes ?? 0, results: [], next: null, previous: null }),
            ),
          )
        }
        if (quality === 'usable') {
          return Promise.resolve(
            new Response(
              JSON.stringify({ count: totals.usableEpisodes ?? 0, results: [], next: null, previous: null }),
            ),
          )
        }
        if (quality === 'bad') {
          return Promise.resolve(
            new Response(
              JSON.stringify({ count: totals.badEpisodes ?? 0, results: [], next: null, previous: null }),
            ),
          )
        }

        return Promise.resolve(
          new Response(
            JSON.stringify({ count: totals.totalEpisodes ?? 60, results: [], next: null, previous: null }),
          ),
        )
      }

      return Promise.resolve(new Response(JSON.stringify({ count: 0, results: [], next: null, previous: null })))
    }),
  )

  return episodesCalls
}

it('uses API status totals even when the recent page contains only one status', async () => {
  stubStaffFetch({
    totalRequests: 60,
    requestStatusCounts: { submitted: 0, in_progress: 0, delivered: 12, accepted: 0, rejected: 0 },
  })

  renderWithProviders(<Dashboard />)

  const label = await screen.findByText('Delivered', { selector: '.card small' })
  const card = label.closest('.card') as HTMLElement
  expect(within(card).getByText('12')).toBeInTheDocument()

  const totalCard = screen.getByText('Requests', { exact: true }).closest('.card') as HTMLElement
  expect(within(totalCard).getByText('60')).toBeInTheDocument()
})

it('shows the staff daily quality bar chart with range filters', async () => {
  stubStaffFetch({
    totalEpisodes: 20,
    availableEpisodes: 6,
    goodEpisodes: 10,
    usableEpisodes: 6,
    badEpisodes: 4,
  })

  const { container } = renderWithProviders(<Dashboard />)

  expect(await screen.findByRole('heading', { name: 'Episode quality' })).toBeInTheDocument()
  const chart = await screen.findByRole('img', { name: /Daily Good, Usable, and Bad episode counts/ })
  expect(chart.querySelectorAll('.quality-column')).toHaveLength(3)
  expect(chart.querySelectorAll('.quality-grid-line')).toHaveLength(4)
  expect(chart.querySelectorAll('.quality-axis-label').length).toBeGreaterThan(4)
  expect(screen.getByRole('button', { name: 'This week' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: 'This month' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Custom' })).toBeInTheDocument()
  expect(screen.getByText(/20 episodes imported/)).toBeInTheDocument()
  expect(container.querySelector('.quality-chart-legend')).toHaveTextContent('Good')
  expect(container.querySelector('.quality-chart-legend')).toHaveTextContent('Usable')
  expect(container.querySelector('.quality-chart-legend')).toHaveTextContent('Bad')
  expect(screen.queryByRole('heading', { name: 'Awaiting your review' })).not.toBeInTheDocument()
})

it('shows client-owned delivered requests with actual counts and refreshes after acceptance', async () => {
  const user = userEvent.setup()
  const deliveredRequests = [
    makeRequest({
      id: 'r-newest',
      task_name: 'Newest client delivery',
      status: 'delivered',
      first_delivered_at: '2026-10-04T10:00:00Z',
      episodes_requested: 20,
      assigned_count: 12,
      allowed_actions: ['accept', 'reject'],
    }),
    makeRequest({
      id: 'r-second',
      task_name: 'Second client delivery',
      status: 'delivered',
      first_delivered_at: '2026-10-03T10:00:00Z',
      assigned_count: 8,
    }),
    makeRequest({
      id: 'r-third',
      task_name: 'Third client delivery',
      status: 'delivered',
      first_delivered_at: '2026-10-02T10:00:00Z',
      assigned_count: 6,
    }),
  ]
  let currentRequest = deliveredRequests[0]!
  const deliveredCalls: string[] = []
  vi.stubGlobal('fetch', vi.fn((input: string | URL | Request, init?: RequestInit) => {
    const inputUrl = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const url = new URL(inputUrl, 'http://localhost')
    const respond = (body: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status }))

    if (url.pathname.endsWith('/auth/me')) {
      return respond(makeUser({ role: 'client', name: 'Client User' }))
    }
    if (url.pathname.endsWith('/auth/csrf')) return respond({ csrf_token: 'test-csrf' })
    if (url.pathname.endsWith('/assignments')) {
      return respond({ results: [], assigned_count: currentRequest.assigned_count, episodes_requested: currentRequest.episodes_requested })
    }
    if (url.pathname.endsWith('/history')) return respond([])
    if (url.pathname.endsWith('/transitions')) {
      const rawBody = typeof init?.body === 'string' ? init.body : '{}'
      const body = JSON.parse(rawBody) as { status: string }
      currentRequest = { ...currentRequest, status: body.status as 'accepted', allowed_actions: [] }
      return respond(currentRequest)
    }
    if (url.pathname === `/api/requests/${currentRequest.id}`) return respond(currentRequest)
    if (url.pathname === '/api/requests') {
      const status = url.searchParams.get('status')
      if (status === 'delivered') {
        deliveredCalls.push(url.search)
        const results = currentRequest.status === 'delivered' ? deliveredRequests : []
        return respond({ count: results.length === 0 ? 0 : 4, results, next: null, previous: null })
      }
      if (status) return respond({ count: 0, results: [], next: null, previous: null })
      return respond({ count: 1, results: [currentRequest], next: null, previous: null })
    }
    return respond({ count: 0, results: [], next: null, previous: null })
  }))

  render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Dashboard />} />
            <Route path="requests/:id" element={<RequestDetail />} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('4 requests')).toBeInTheDocument()
  expect(screen.getByText('12 assigned episodes')).toBeInTheDocument()
  expect(screen.getByText('20 episode(s) requested')).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: /^Review / })).toHaveLength(3)
  expect(screen.getByRole('link', { name: /View all delivered requests/ })).toHaveAttribute(
    'href',
    '/requests?status=delivered',
  )
  expect(deliveredCalls).toHaveLength(1)
  expect(new URLSearchParams(deliveredCalls[0]).get('page_size')).toBe('3')

  await user.click(screen.getByRole('link', { name: 'Review Newest client delivery' }))
  expect(await screen.findByRole('heading', { name: 'Request details' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Accept delivery' }))
  expect(await screen.findByText('Request marked accepted.')).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'Overview' }))

  expect(await screen.findByText('No requests awaiting review.')).toBeInTheDocument()
  expect(deliveredCalls).toHaveLength(2)
})

it('shows only chart axes when no quality data exists', async () => {
  stubStaffFetch({
    totalEpisodes: 0,
    availableEpisodes: 0,
    goodEpisodes: 0,
    usableEpisodes: 0,
    badEpisodes: 0,
  })

  const { container } = renderWithProviders(<Dashboard />)

  const chart = await screen.findByRole('img', { name: /Daily Good, Usable, and Bad episode counts/ })
  expect(chart.querySelectorAll('.quality-grid-line')).toHaveLength(4)
  expect(chart.querySelector('.quality-axis-line')).not.toBeNull()
  expect(container.querySelectorAll('.quality-column')).toHaveLength(0)
})

it('does not request the staff quality series for a client', async () => {
  const episodeCalls: string[] = []
  const qualityCalls: string[] = []
  vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
    const urlStr = typeof input === 'string' ? input : (input as Request).url
    const url = new URL(urlStr, 'http://localhost')

    if (url.pathname.endsWith('/auth/me')) {
      return Promise.resolve(new Response(JSON.stringify(makeUser({ role: 'client', name: 'Ava Client' }))))
    }

    if (url.pathname.endsWith('/episodes')) {
      episodeCalls.push(url.search)
    }
    if (url.pathname.endsWith('/episode-quality')) {
      qualityCalls.push(url.search)
    }

    if (url.pathname.endsWith('/requests')) {
      return Promise.resolve(
        new Response(JSON.stringify({ count: 0, results: [], next: null, previous: null })),
      )
    }

    return Promise.resolve(new Response(JSON.stringify({ count: 0, results: [], next: null, previous: null })))
  }))

  renderWithProviders(<Dashboard />)

  expect(await screen.findByText('Request pipeline')).toBeInTheDocument()
  expect(episodeCalls).toHaveLength(0)
  expect(qualityCalls).toHaveLength(0)
})
