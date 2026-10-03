/**
 * API client behaviour.
 *
 * These cover the things that would be silent security or correctness bugs:
 * whether the CSRF header actually goes out, whether credentials are sent,
 * and whether a 401 resets the session.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api, ensureCsrfToken, setUnauthenticatedHandler } from './client'
import { urlOf } from '../test/helpers'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthenticatedHandler(null)
  // Clear the CSRF cookie between tests so the handshake is exercised afresh.
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

describe('CSRF handling', () => {
  it('fetches a token before an unsafe request and sends it as a header', async () => {
    const fetchMock = vi.fn((input: string | URL | Request, init?: RequestInit) => {
      const url = urlOf(input)
      if (url.includes('/auth/csrf')) {
        return Promise.resolve(jsonResponse({ csrf_token: 'token-abc' }))
      }
      expect(new Headers(init?.headers).get('X-CSRFToken')).toBe('token-abc')
      return Promise.resolve(jsonResponse({ id: 'u-1' }))
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.login('a@example.com', 'password')

    // The handshake happened, then the login.
    const firstCall = fetchMock.mock.calls[0]?.[0]
    expect(firstCall && urlOf(firstCall)).toContain('/auth/csrf')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('reuses an existing cookie instead of re-fetching the token', async () => {
    document.cookie = 'csrftoken=cookie-token'
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse({})))
    vi.stubGlobal('fetch', fetchMock)

    const token = await ensureCsrfToken()

    expect(token).toBe('cookie-token')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not send a CSRF header on a safe request', async () => {
    const fetchMock = vi.fn((_input: string | URL | Request, init?: RequestInit) => {
      expect(new Headers(init?.headers).get('X-CSRFToken')).toBeNull()
      return Promise.resolve(jsonResponse({ id: 'u-1' }))
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.me()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('always sends credentials so the session cookie travels', async () => {
    const fetchMock = vi.fn((_input: string | URL | Request, init?: RequestInit) => {
      expect(init?.credentials).toBe('same-origin')
      return Promise.resolve(jsonResponse({ count: 0, results: [] }))
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.listRequests()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('error handling', () => {
  it('parses the error envelope into an ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            {
              error: {
                code: 'validation_error',
                message: 'The submitted data is invalid.',
                fields: { deadline: ['Choose a deadline on or after 2026-10-03.'] },
              },
              request_id: 'req-9',
            },
            400,
          ),
        ),
      ),
    )

    await expect(api.listRequests()).rejects.toMatchObject({
      status: 400,
      code: 'validation_error',
      requestId: 'req-9',
    })

    try {
      await api.listRequests()
      expect.unreachable('should have thrown')
    } catch (caught) {
      expect(caught).toBeInstanceOf(ApiError)
      // Field errors are reachable so a form can render them inline.
      expect((caught as ApiError).fieldError('deadline')).toContain('2026-10-03')
    }
  })

  it('marks a 409 as a conflict so callers know to refetch', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            {
              error: { code: 'conflict', message: '1 of 3 episodes assigned.' },
              request_id: 'req-1',
            },
            409,
          ),
        ),
      ),
    )

    try {
      await api.listRequests()
      expect.unreachable('should have thrown')
    } catch (caught) {
      expect((caught as ApiError).isConflict).toBe(true)
    }
  })

  it('notifies the unauthenticated handler exactly once per 401', async () => {
    const onUnauthenticated = vi.fn()
    setUnauthenticatedHandler(onUnauthenticated)
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            {
              error: { code: 'unauthenticated', message: 'Authentication is required.' },
              request_id: null,
            },
            401,
          ),
        ),
      ),
    )

    await expect(api.me()).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthenticated).toHaveBeenCalledTimes(1)
  })

  it('survives a non-JSON error body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('<html>502 upstream</html>', { status: 502 }))),
    )

    // A proxy error page must become a readable message, not a parse crash.
    await expect(api.me()).rejects.toMatchObject({ status: 502 })
  })

  it('returns undefined for a 204 without trying to parse a body', async () => {
    document.cookie = 'csrftoken=t'
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))))

    await expect(api.removeAssignment('r-1', 'a-1')).resolves.toBeUndefined()
  })
})

describe('request shaping', () => {
  it('omits empty query parameters', async () => {
    const fetchMock = vi.fn((input: string | URL | Request) => {
      expect(urlOf(input)).toBe('/api/requests?page=2')
      return Promise.resolve(jsonResponse({ count: 0, results: [] }))
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.listRequests({ page: 2, status: '', search: '' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('sends an upload as multipart without forcing a Content-Type', async () => {
    document.cookie = 'csrftoken=t'
    const fetchMock = vi.fn((_input: string | URL | Request, init?: RequestInit) => {
      expect(init?.body).toBeInstanceOf(FormData)
      // The browser must set the multipart boundary itself.
      expect(new Headers(init?.headers).get('Content-Type')).toBeNull()
      return Promise.resolve(jsonResponse({ imported: 1 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.importEpisodes(new File(['episode_id\n'], 'episodes.csv', { type: 'text/csv' }))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
