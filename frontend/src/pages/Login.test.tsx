/**
 * Login and role-driven navigation.
 *
 * The navigation assertions are about usability, not security: they check
 * that a client is not shown staff screens they cannot use. The server
 * refusing those endpoints is covered by the backend suite.
 */

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from '../App'
import { makeUser, paginated, renderWithProviders, stubFetch } from '../test/helpers'

afterEach(() => {
  vi.unstubAllGlobals()
})

const BASE = {
  'GET /api/auth/csrf': { body: { csrf_token: 'token' } },
  'GET /api/requests': { body: paginated([]) },
  'GET /api/episodes': { body: paginated([]) },
}

function anonymous(overrides = {}) {
  return {
    ...BASE,
    'GET /api/auth/me': {
      status: 401,
      body: {
        error: { code: 'unauthenticated', message: 'Authentication is required.' },
        request_id: null,
      },
    },
    ...overrides,
  }
}

describe('login form', () => {
  it('shows the login screen when there is no session', async () => {
    stubFetch(anonymous())
    renderWithProviders(<App />, { route: '/', path: '*' })

    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
    expect(screen.getByLabelText('Email address')).toBeInTheDocument()
  })

  it('sends the credentials and shows the workspace on success', async () => {
    const stub = stubFetch(
      anonymous({
        'POST /api/auth/login': { body: makeUser({ role: 'client' }) },
      }),
    )
    renderWithProviders(<App />, { route: '/', path: '*' })

    await userEvent.type(
      await screen.findByLabelText('Email address'),
      'client-a@example.com',
    )
    await userEvent.type(screen.getByLabelText('Password'), 'client123')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => {
      expect(stub.lastCall('/api/auth/login')?.body).toEqual({
        email: 'client-a@example.com',
        password: 'client123',
      })
    })
    expect(await screen.findByText('Workspace / Overview')).toBeInTheDocument()
  })

  it('shows the server message verbatim on a bad password', async () => {
    stubFetch(
      anonymous({
        'POST /api/auth/login': {
          status: 401,
          body: {
            error: {
              code: 'invalid_credentials',
              message: 'Incorrect email or password.',
            },
            request_id: 'r-1',
          },
        },
      }),
    )
    renderWithProviders(<App />, { route: '/', path: '*' })

    await userEvent.type(await screen.findByLabelText('Email address'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    // Deliberately the same wording the server uses for every failure mode,
    // so the form cannot be used to discover which emails have accounts.
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Incorrect email or password.',
    )
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
  })

  it('fills the form from a demo account button without signing in', async () => {
    const stub = stubFetch(anonymous())
    renderWithProviders(<App />, { route: '/', path: '*' })

    await userEvent.click(
      await screen.findByRole('button', { name: /Olu Operator/ }),
    )

    expect(screen.getByLabelText('Email address')).toHaveValue('ops1@example.com')
    expect(screen.getByLabelText('Password')).toHaveValue('ops123')
    // Filling the fields must not be a login by itself.
    expect(stub.calls.filter((call) => call.url.includes('/auth/login'))).toHaveLength(0)
  })
})

describe('navigation by role', () => {
  it('shows a client only their own screens', async () => {
    stubFetch({ ...BASE, 'GET /api/auth/me': { body: makeUser({ role: 'client' }) } })
    renderWithProviders(<App />, { route: '/', path: '*' })

    await screen.findByText('Workspace / Overview')
    expect(screen.getByRole('link', { name: /My requests/ })).toBeInTheDocument()
    for (const label of ['Episodes', 'Analytics', 'Users']) {
      expect(screen.queryByRole('link', { name: new RegExp(label) })).not.toBeInTheDocument()
    }
  })

  it('shows an operator the staff screens but not Users', async () => {
    stubFetch({ ...BASE, 'GET /api/auth/me': { body: makeUser({ role: 'operator' }) } })
    renderWithProviders(<App />, { route: '/', path: '*' })

    await screen.findByText('Workspace / Overview')
    expect(screen.getByRole('link', { name: /Episodes/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Analytics/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Users/ })).not.toBeInTheDocument()
  })

  it('shows an admin the Users screen as well', async () => {
    stubFetch({
      ...BASE,
      'GET /api/auth/me': { body: makeUser({ role: 'admin' }) },
      'GET /api/users': { body: paginated([]) },
    })
    renderWithProviders(<App />, { route: '/', path: '*' })

    await screen.findByText('Workspace / Overview')
    expect(screen.getByRole('link', { name: /Users/ })).toBeInTheDocument()
  })

  it('redirects a client away from a staff route', async () => {
    stubFetch({ ...BASE, 'GET /api/auth/me': { body: makeUser({ role: 'client' }) } })
    renderWithProviders(<App />, { route: '/episodes', path: '*' })

    // Lands on the overview instead of an empty staff page.
    await screen.findByText('Workspace / Overview')
    expect(screen.queryByRole('button', { name: /Import CSV/ })).not.toBeInTheDocument()
  })
})

describe('session expiry', () => {
  it('returns to the login screen when a call reports 401', async () => {
    stubFetch({
      ...BASE,
      'GET /api/auth/me': { body: makeUser({ role: 'client' }) },
      // The session dies between the initial load and this call.
      'GET /api/requests': {
        status: 401,
        body: {
          error: { code: 'unauthenticated', message: 'Authentication is required.' },
          request_id: null,
        },
      },
    })
    renderWithProviders(<App />, { route: '/requests', path: '*' })

    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
  })
})
