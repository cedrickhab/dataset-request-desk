import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'

import { makeRequest } from '../test/helpers'
import { ClientReviewCard } from './ClientReviewCard'

it('shows a compact row skeleton while review data loads', () => {
  const reload = vi.fn()
  const { container } = render(
    <MemoryRouter>
      <ClientReviewCard state={{ data: null, loading: true, error: null, reload }} />
    </MemoryRouter>,
  )

  expect(screen.getByRole('status', { name: 'Loading delivered requests' })).toBeInTheDocument()
  expect(container.querySelectorAll('.review-skeleton-row')).toHaveLength(3)
})

it('shows an accurate singular count and actual assigned episode count', () => {
  const request = makeRequest({
    id: 'r-one',
    task_name: 'One delivered task',
    status: 'delivered',
    episodes_requested: 20,
    assigned_count: 12,
  })
  render(
    <MemoryRouter>
      <ClientReviewCard
        state={{
          data: { count: 1, next: null, previous: null, results: [request] },
          loading: false,
          error: null,
          reload: vi.fn(),
        }}
      />
    </MemoryRouter>,
  )

  expect(screen.getByText('1 request')).toBeInTheDocument()
  expect(screen.getByText('12 assigned episodes')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Review One delivered task' })).toHaveAttribute(
    'href',
    '/requests/r-one',
  )
  expect(screen.queryByText('20 assigned episodes')).not.toBeInTheDocument()
})

it('shows at most three delivered rows and links the true total to the delivered filter', () => {
  const requests = ['a', 'b', 'c', 'd'].map((id) =>
    makeRequest({ id, task_name: `Task ${id}`, status: 'delivered' }),
  )
  render(
    <MemoryRouter>
      <ClientReviewCard
        state={{
          data: { count: 7, next: null, previous: null, results: requests },
          loading: false,
          error: null,
          reload: vi.fn(),
        }}
      />
    </MemoryRouter>,
  )

  expect(screen.getByText('7 requests')).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: /^Review Task/ })).toHaveLength(3)
  expect(screen.queryByText('Task d')).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: /View all delivered requests/ })).toHaveAttribute(
    'href',
    '/requests?status=delivered',
  )
})

it('shows the specified empty state', () => {
  render(
    <MemoryRouter>
      <ClientReviewCard
        state={{
          data: { count: 0, next: null, previous: null, results: [] },
          loading: false,
          error: null,
          reload: vi.fn(),
        }}
      />
    </MemoryRouter>,
  )

  expect(screen.getByText('No requests awaiting review.')).toBeInTheDocument()
  expect(screen.getByText('Delivered requests will appear here.')).toBeInTheDocument()
})

it('shows a concise error and retries', async () => {
  const user = userEvent.setup()
  const reload = vi.fn()
  render(
    <MemoryRouter>
      <ClientReviewCard
        state={{ data: null, loading: false, error: 'Request failed.', reload }}
      />
    </MemoryRouter>,
  )

  expect(screen.getByRole('alert')).toHaveTextContent('Could not load delivered requests.')
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(reload).toHaveBeenCalledOnce()
})
