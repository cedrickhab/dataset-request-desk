/**
 * Request detail behaviour.
 *
 * The thing worth testing here is that the UI obeys the server's
 * `allowed_actions` rather than deciding for itself, and that it recovers
 * when the server refuses a stale action.
 */

import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RequestDetail } from './RequestDetail'
import {
  makeEpisode,
  makeRequest,
  makeUser,
  paginated,
  renderWithProviders,
  stubFetch,
} from '../test/helpers'

function routes(overrides: Record<string, { body?: unknown; status?: number }> = {}) {
  return {
    'GET /api/auth/me': { body: makeUser({ role: 'operator', name: 'Olu Operator' }) },
    'GET /api/auth/csrf': { body: { csrf_token: 'token' } },
    'GET /api/requests/r-1': { body: makeRequest() },
    'GET /api/requests/r-1/assignments': {
      body: { results: [], assigned_count: 0, episodes_requested: 2 },
    },
    'GET /api/requests/r-1/history': {
      body: [
        {
          id: 'h-1',
          previous_status: null,
          new_status: 'submitted',
          actor_id: 'u-1',
          actor_name: 'Acme Robotics',
          reason: '',
          created_at: '2026-09-20T09:00:00Z',
        },
      ],
    },
    ...overrides,
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('actions follow the server', () => {
  it('shows Start work only when the server allows it', async () => {
    stubFetch(
      routes({
        'GET /api/requests/r-1': {
          body: makeRequest({ status: 'submitted', allowed_actions: ['start_work'] }),
        },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    expect(await screen.findByRole('button', { name: 'Start work' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Assign episodes/ })).not.toBeInTheDocument()
  })

  it('offers no actions when the server returns none', async () => {
    stubFetch(
      routes({
        'GET /api/requests/r-1': {
          body: makeRequest({ status: 'accepted', allowed_actions: [] }),
        },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    await screen.findByText('pick cup')
    for (const label of ['Start work', 'Restart work', 'Mark as delivered', 'Accept delivery']) {
      expect(screen.queryByRole('button', { name: label })).not.toBeInTheDocument()
    }
  })

  it('disables Mark as delivered while the count is short and explains why', async () => {
    stubFetch(
      routes({
        'GET /api/requests/r-1': {
          body: makeRequest({
            status: 'in_progress',
            assigned_count: 1,
            episodes_requested: 3,
            // 'deliver' is absent because the server withheld it.
            allowed_actions: ['assign'],
          }),
        },
        'GET /api/requests/r-1/assignments': {
          body: {
            results: [
              {
                id: 'a-1',
                episode: makeEpisode(),
                export_job: {
                  status: 'completed',
                  attempts: 1,
                  max_attempts: 3,
                  last_error: '',
                  completed_at: '2026-09-21T10:00:00Z',
                },
                assigned_by_name: 'Olu Operator',
                assigned_at: '2026-09-21T09:00:00Z',
              },
            ],
            assigned_count: 1,
            episodes_requested: 3,
          },
        },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    const deliver = await screen.findByRole('button', { name: 'Mark as delivered' })
    expect(deliver).toBeDisabled()
    // The shortfall is stated, not left for the user to work out.
    expect(await screen.findByText(/Assign 2 more episode/)).toBeInTheDocument()
  })

  it('enables Mark as delivered once the server says deliver is allowed', async () => {
    stubFetch(
      routes({
        'GET /api/requests/r-1': {
          body: makeRequest({
            status: 'in_progress',
            assigned_count: 2,
            allowed_actions: ['assign', 'deliver'],
          }),
        },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    expect(await screen.findByRole('button', { name: 'Mark as delivered' })).toBeEnabled()
  })

  it('shows a client accept and reject on a delivered request', async () => {
    stubFetch(
      routes({
        'GET /api/auth/me': { body: makeUser({ role: 'client' }) },
        'GET /api/requests/r-1': {
          body: makeRequest({ status: 'delivered', allowed_actions: ['accept', 'reject'] }),
        },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    expect(await screen.findByRole('button', { name: 'Accept delivery' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject delivery' })).toBeInTheDocument()
    // A client never gets episode-management controls.
    expect(screen.queryByRole('button', { name: /Remove/ })).not.toBeInTheDocument()
  })
})

describe('server refusals', () => {
  it('shows the conflict message and refetches when a transition is refused', async () => {
    const stub = stubFetch(
      routes({
        'GET /api/requests/r-1': {
          body: makeRequest({ status: 'submitted', allowed_actions: ['start_work'] }),
        },
        'POST /api/requests/r-1/transitions': {
          status: 409,
          body: {
            error: {
              code: 'conflict',
              message: 'A submitted request cannot move to delivered.',
            },
            request_id: 'req-1',
          },
        },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    await userEvent.click(await screen.findByRole('button', { name: 'Start work' }))

    expect(
      await screen.findByText('A submitted request cannot move to delivered.'),
    ).toBeInTheDocument()

    // Stale view corrected: the request was reloaded after the refusal.
    await waitFor(() => {
      const detailCalls = stub.calls.filter(
        (call) => call.method === 'GET' && call.url === '/api/requests/r-1',
      )
      expect(detailCalls.length).toBeGreaterThan(1)
    })
  })

  it('confirms before rejecting rather than firing immediately', async () => {
    const stub = stubFetch(
      routes({
        'GET /api/auth/me': { body: makeUser({ role: 'client' }) },
        'GET /api/requests/r-1': {
          body: makeRequest({ status: 'delivered', allowed_actions: ['accept', 'reject'] }),
        },
        'POST /api/requests/r-1/transitions': { body: makeRequest({ status: 'rejected' }) },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    await userEvent.click(await screen.findByRole('button', { name: 'Reject delivery' }))

    // Nothing sent yet: a dialog opened instead.
    expect(
      stub.calls.filter((call) => call.url.includes('/transitions')),
    ).toHaveLength(0)

    const dialog = screen.getByRole('dialog', { name: /Reject this delivery/ })
    await userEvent.type(
      within(dialog).getByLabelText(/Reason/),
      'Cup is out of frame',
    )
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reject delivery' }))

    await waitFor(() => {
      const sent = stub.lastCall('/transitions')
      expect(sent?.body).toEqual({ status: 'rejected', reason: 'Cup is out of frame' })
    })
  })
})

describe('export status', () => {
  it('renders per-episode status with attempts and a sanitized message', async () => {
    stubFetch(
      routes({
        'GET /api/requests/r-1/assignments': {
          body: {
            results: [
              {
                id: 'a-1',
                episode: makeEpisode(),
                export_job: {
                  status: 'retry_wait',
                  attempts: 1,
                  max_attempts: 3,
                  last_error: 'export simulation failed; scheduled for retry',
                  completed_at: null,
                },
                assigned_by_name: 'Olu Operator',
                assigned_at: '2026-09-21T09:00:00Z',
              },
            ],
            assigned_count: 1,
            episodes_requested: 2,
          },
        },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    expect(await screen.findByText('Waiting to retry')).toBeInTheDocument()
    expect(screen.getByText(/Attempt 1 of 3/)).toBeInTheDocument()
  })

  it('never renders a download link for a completed export', async () => {
    stubFetch(
      routes({
        'GET /api/requests/r-1/assignments': {
          body: {
            results: [
              {
                id: 'a-1',
                episode: makeEpisode(),
                export_job: {
                  status: 'completed',
                  attempts: 1,
                  max_attempts: 3,
                  last_error: '',
                  completed_at: '2026-09-21T10:00:00Z',
                },
                assigned_by_name: 'Olu Operator',
                assigned_at: '2026-09-21T09:00:00Z',
              },
            ],
            assigned_count: 1,
            episodes_requested: 2,
          },
        },
      }),
    )
    const { container } = renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    await screen.findByText('Completed')
    // No artifact exists, so offering one would be a lie. Checked as the
    // absence of any link or URL, not the absence of the word "download" --
    // the help text legitimately says no files are produced or downloaded.
    expect(container.querySelector('a[download]')).toBeNull()
    expect(container.querySelector('a[href^="http"]')).toBeNull()
    expect(container.querySelector('a[href$=".mp4"]')).toBeNull()
    expect(screen.queryByRole('button', { name: /download/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /download/i })).not.toBeInTheDocument()
  })
})

describe('assignment dialog', () => {
  it('requests only eligible episodes for this task', async () => {
    const stub = stubFetch(
      routes({
        'GET /api/requests/r-1': {
          body: makeRequest({
            status: 'in_progress',
            allowed_actions: ['assign'],
          }),
        },
        'GET /api/episodes': { body: paginated([makeEpisode()]) },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    await userEvent.click(await screen.findByRole('button', { name: /Assign episodes/ }))

    await waitFor(() => {
      const call = stub.lastCall('/api/episodes')
      expect(call).toBeDefined()
      // Scoped by task and availability so a mismatched or reserved episode
      // is never even offered.
      expect(call?.url).toContain('task_name=pick+cup')
      expect(call?.url).toContain('available=true')
    })
  })

  it('keeps the submit button disabled until something is selected', async () => {
    stubFetch(
      routes({
        'GET /api/requests/r-1': {
          body: makeRequest({ status: 'in_progress', allowed_actions: ['assign'] }),
        },
        'GET /api/episodes': { body: paginated([makeEpisode()]) },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    await userEvent.click(await screen.findByRole('button', { name: /Assign episodes/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Assign episodes' })

    expect(within(dialog).getByRole('button', { name: /^Assign/ })).toBeDisabled()

    await userEvent.click(await within(dialog).findByLabelText('Select EP-00001'))
    expect(within(dialog).getByRole('button', { name: /^Assign/ })).toBeEnabled()
  })

  it('sends the selected episode ids and reports a conflict', async () => {
    const stub = stubFetch(
      routes({
        'GET /api/requests/r-1': {
          body: makeRequest({ status: 'in_progress', allowed_actions: ['assign'] }),
        },
        'GET /api/episodes': { body: paginated([makeEpisode()]) },
        'POST /api/requests/r-1/assignments': {
          status: 409,
          body: {
            error: {
              code: 'conflict',
              message: 'EP-00001 is already reserved for another request.',
            },
            request_id: 'req-2',
          },
        },
      }),
    )
    renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })

    await userEvent.click(await screen.findByRole('button', { name: /Assign episodes/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Assign episodes' })
    await userEvent.click(await within(dialog).findByLabelText('Select EP-00001'))
    await userEvent.click(within(dialog).getByRole('button', { name: /^Assign/ }))

    await waitFor(() => {
      expect(stub.lastCall('/r-1/assignments')?.body).toEqual({ episode_ids: ['e-1'] })
    })
    expect(
      await screen.findByText('EP-00001 is already reserved for another request.'),
    ).toBeInTheDocument()
  })
})

it('polls active export jobs, then stops after completion', async () => {
  const assignment = {
    id: 'a-1', episode: makeEpisode(), assigned_by_name: 'Olu Operator',
    assigned_at: '2026-09-20T09:00:00Z',
    export_job: { status: 'pending', attempts: 0, max_attempts: 3, last_error: '' },
  }
  const responses = routes({
    'GET /api/requests/r-1/assignments': {
      body: { results: [assignment], assigned_count: 1, episodes_requested: 2 },
    },
  })
  const stub = stubFetch(responses)
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  vi.useFakeTimers()
  try {
    await act(async () => {
      renderWithProviders(<RequestDetail />, { route: '/requests/r-1', path: '/requests/:id' })
      await Promise.resolve()
    })
    expect(screen.getByText('Pending')).toBeInTheDocument()
    assignment.export_job.status = 'completed'
    await act(async () => { await vi.advanceTimersByTimeAsync(3100) })
    expect(screen.getByText('Completed')).toBeInTheDocument()
    const count = stub.calls.filter((call) => call.url.endsWith('/assignments')).length
    expect(count).toBeGreaterThan(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(stub.calls.filter((call) => call.url.endsWith('/assignments'))).toHaveLength(count)
  } finally {
    vi.useRealTimers()
    vi.restoreAllMocks()
  }
})
