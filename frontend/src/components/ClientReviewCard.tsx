import type { DatasetRequest, Paginated } from '../api/types'
import type { AsyncState } from '../api/useAsync'
import { Link } from 'react-router-dom'
import { Icon } from './Icon'
import { StatusBadge } from './ui'

export function ClientReviewCard({
  state,
}: {
  state: AsyncState<Paginated<DatasetRequest> | null>
}) {
  const count = state.data?.count
  const requests = state.data?.results
    .filter((request) => request.status === 'delivered')
    .slice(0, 3) ?? []

  return (
    <section className="panel client-review-card" aria-labelledby="client-review-title">
      <header className="review-card-header">
        <div>
          <h2 id="client-review-title">Awaiting your review</h2>
          <p className="sub">Delivered requests ready for your decision.</p>
        </div>
        {state.loading && !state.data ? (
          <span className="skeleton review-count-skeleton" aria-label="Loading request count" />
        ) : (
          <span className="review-count">
            {count === undefined ? '—' : count} {count === 1 ? 'request' : 'requests'}
          </span>
        )}
      </header>

      {state.error ? (
        <div className="review-error" role="alert">
          <span>Could not load delivered requests.</span>
          <button type="button" onClick={state.reload}>Retry</button>
        </div>
      ) : state.loading && !state.data ? (
        <div className="review-skeleton" role="status" aria-label="Loading delivered requests">
          {[0, 1, 2].map((row) => (
            <div className="review-skeleton-row" key={row}>
              <span className="skeleton review-skeleton-icon" />
              <span className="review-skeleton-copy">
                <span className="skeleton review-skeleton-title" />
                <span className="skeleton review-skeleton-subtitle" />
                <span className="skeleton review-skeleton-badge" />
              </span>
              <span className="skeleton review-skeleton-action" />
            </div>
          ))}
        </div>
      ) : requests.length === 0 ? (
        <div className="review-empty">
          <p>No requests awaiting review.</p>
          <small>Delivered requests will appear here.</small>
        </div>
      ) : (
        <>
          <ul className="review-list">
            {requests.map((request) => (
              <ReviewRequestRow key={request.id} request={request} />
            ))}
          </ul>
          {(count ?? 0) > 3 ? (
            <Link className="review-all" to="/requests?status=delivered">
              View all delivered requests <span aria-hidden="true">→</span>
            </Link>
          ) : null}
        </>
      )}
    </section>
  )
}

function ReviewRequestRow({ request }: { request: DatasetRequest }) {
  return (
    <li className="review-request">
      <span className="review-icon">
        <Icon name="file-text" size={30} />
      </span>
      <div className="review-copy">
        <h3 className="review-title">{request.task_name}</h3>
        <p className="review-assigned">
          {request.assigned_count} assigned episode{request.assigned_count === 1 ? '' : 's'}
        </p>
        <StatusBadge status="delivered" />
      </div>
      <Link
        className="review-button"
        to={`/requests/${request.id}`}
        aria-label={`Review ${request.task_name}`}
      >
        Review
      </Link>
    </li>
  )
}
