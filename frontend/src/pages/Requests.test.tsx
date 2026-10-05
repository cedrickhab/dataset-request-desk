import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/AuthContext'
import { Pagination } from '../components/ui'
import { makeRequest, makeUser, paginated, renderWithProviders, stubFetch } from '../test/helpers'
import { RequestTable } from './Requests'
import { Requests } from './Requests'
import { RequestDetail } from './RequestDetail'

it('shows an Open action for each request and keeps its ID out of the task link', () => {
  renderWithProviders(
    <RequestTable
      rows={[makeRequest({ id: 'request-42', task_name: 'pick cup' })]}
      showClient={false}
    />,
  )

  const link = screen.getByRole('link', { name: 'Open' })
  expect(link).toHaveAttribute(
    'href',
    '/requests/request-42',
  )
  expect(screen.queryByRole('link', { name: 'request-42' })).not.toBeInTheDocument()
  expect(screen.queryByText('View')).not.toBeInTheDocument()
})

it('opens request details when Open is clicked', async () => {
  const user = userEvent.setup()
  const request = makeRequest({ id: 'r-1' })
  stubFetch({
    'GET /api/auth/me': { body: makeUser() },
    'GET /api/requests': { body: paginated([request]) },
    'GET /api/requests/r-1': { body: request },
    'GET /api/requests/r-1/assignments': {
      body: { results: [], assigned_count: 0, episodes_requested: 2 },
    },
    'GET /api/requests/r-1/history': { body: [] },
  })

  render(
    <MemoryRouter initialEntries={['/requests']}>
      <AuthProvider>
        <Routes>
          <Route path="/requests" element={<Requests />} />
          <Route path="/requests/:id" element={<RequestDetail />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )

  await user.click(await screen.findByRole('link', { name: 'Open' }))
  expect(await screen.findByRole('heading', { name: 'Request details' })).toBeInTheDocument()
})

it('shows numbered pagination without Next or Previous controls', async () => {
  const user = userEvent.setup()
  const onPage = vi.fn()
  render(<Pagination page={1} count={21} pageSize={10} onPage={onPage} />)

  expect(screen.queryByRole('button', { name: 'Previous' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Page 2' }))
  expect(onPage).toHaveBeenCalledWith(2)
})

it('does not render pagination for ten or fewer rows', () => {
  const onPage = vi.fn()
  const { container } = render(
    <Pagination page={1} count={10} pageSize={10} onPage={onPage} />,
  )

  expect(container.querySelector('.pagination')).not.toBeInTheDocument()
})

it('opens the existing request list with its delivered filter applied', async () => {
  const stub = stubFetch({
    'GET /api/auth/me': { body: makeUser() },
    'GET /api/requests': { body: paginated([]) },
  })

  renderWithProviders(<Requests />, {
    route: '/requests?status=delivered',
    path: '/requests',
  })

  expect(await screen.findByLabelText('Filter by status')).toHaveValue('delivered')
  const requestCall = stub.lastCall('/api/requests')
  expect(requestCall).toBeDefined()
  expect(new URL(requestCall!.url, 'http://localhost').searchParams.get('status')).toBe('delivered')
})
