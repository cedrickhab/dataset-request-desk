/**
 * Test helpers.
 *
 * Fetch is stubbed per test rather than mocking our own client, so the tests
 * exercise the real CSRF handshake, the real error parsing and the real
 * session handling. Asserting that a mock of `api` returns what we told it to
 * would prove nothing.
 */

import { render, type RenderResult } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import type { ReactElement } from 'react'

import { AuthProvider } from '../auth/AuthContext'
import type { DatasetRequest, Episode, User } from '../api/types'

/**
 * Resolve a fetch input to its URL string.
 *
 * `Request` has no useful toString, so calling it on the union would yield
 * "[object Object]" for that branch and silently break every URL assertion.
 */
export function urlOf(input: string | URL | Request): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.href
  return input.url
}

export interface StubRoute {
  /** Matched against `${method} ${pathname}`, e.g. 'GET /api/requests'. */
  body?: unknown
  status?: number
}

export interface FetchStub {
  calls: { method: string; url: string; body: unknown; headers: Headers }[]
  /** Last request made to a path, for asserting what the UI actually sent. */
  lastCall: (match: string) => { method: string; url: string; body: unknown } | undefined
}

/**
 * Install a fetch stub.
 *
 * Routes are keyed by `METHOD /path`; the first matching prefix wins, so a
 * test can override one endpoint and leave the rest.
 */
export function stubFetch(routes: Record<string, StubRoute>): FetchStub {
  const calls: FetchStub['calls'] = []

  vi.stubGlobal(
    'fetch',
    vi.fn((input: string | URL | Request, init?: RequestInit) => {
      const url = urlOf(input)
      const method = (init?.method ?? 'GET').toUpperCase()
      const headers = new Headers(init?.headers)
      let parsedBody: unknown = null
      if (typeof init?.body === 'string') {
        try {
          parsedBody = JSON.parse(init.body)
        } catch {
          parsedBody = init.body
        }
      } else if (init?.body instanceof FormData) {
        parsedBody = init.body
      }
      calls.push({ method, url, body: parsedBody, headers })

      const path = url.split('?')[0] ?? url
      const key = `${method} ${path}`
      const route = routes[key]

      if (!route) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error: { code: 'not_found', message: `No stub for ${key}` },
              request_id: 'test',
            }),
            { status: 404, headers: { 'Content-Type': 'application/json' } },
          ),
        )
      }

      const status = route.status ?? 200
      if (status === 204) return Promise.resolve(new Response(null, { status }))
      return Promise.resolve(
        new Response(JSON.stringify(route.body ?? {}), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )

  return {
    calls,
    lastCall: (match) => [...calls].reverse().find((call) => call.url.includes(match)),
  }
}

/**
 * Render inside the router and auth provider.
 *
 * `path` must be given whenever the component reads route params, so that
 * useParams resolves exactly as it does in the real app.
 */
export function renderWithProviders(
  element: ReactElement,
  { route = '/', path }: { route?: string; path?: string } = {},
): RenderResult {
  const pattern = path ?? route
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <Routes>
          <Route path={pattern} element={element} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

// --- fixtures ---

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 'u-1',
    name: 'Acme Robotics',
    email: 'client-a@example.com',
    role: 'client',
    organisation: 'Acme Robotics',
    is_active: true,
    created_at: '2026-09-01T10:00:00Z',
    ...overrides,
  }
}

export function makeRequest(overrides: Partial<DatasetRequest> = {}): DatasetRequest {
  return {
    id: 'r-1',
    client_id: 'u-1',
    client_name: 'Acme Robotics',
    task_name: 'pick cup',
    episodes_requested: 2,
    deadline: '2026-10-20',
    notes: 'Clear view of the cup.',
    status: 'submitted',
    assigned_count: 0,
    allowed_actions: [],
    created_at: '2026-09-20T09:00:00Z',
    updated_at: '2026-09-20T09:00:00Z',
    first_delivered_at: null,
    ...overrides,
  }
}

export function makeEpisode(overrides: Partial<Episode> = {}): Episode {
  return {
    id: 'e-1',
    episode_id: 'EP-00001',
    robot_id: 'arm-01',
    task_name: 'pick cup',
    recorded_at: '2026-09-01T12:00:00Z',
    duration_seconds: '42.00',
    operator_name: 'Aline',
    quality: 'good',
    imported_at: '2026-09-02T08:00:00Z',
    assigned_request_id: null,
    ...overrides,
  }
}

export function paginated<T>(results: T[]) {
  return { count: results.length, next: null, previous: null, results }
}
