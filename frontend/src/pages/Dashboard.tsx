/**
 * Overview.
 *
 * Counts here are derived from the request list the viewer can already see,
 * so a client's dashboard is scoped by the same server-side filter as their
 * list. Nothing on this page calls the analytics endpoint: a client has no
 * access to it, and showing staff aggregates here would be a second, parallel
 * definition of the same numbers.
 */

import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import type { DatasetRequest, RequestStatus } from '../api/types'
import { useRoles } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import {
  BarRow,
  EmptyState,
  ErrorBox,
  Loading,
  MetricCard,
  PageHeading,
} from '../components/ui'
import { RequestTable } from './Requests'

const PIPELINE: RequestStatus[] = [
  'submitted',
  'in_progress',
  'delivered',
  'accepted',
  'rejected',
]

const LABELS: Record<RequestStatus, string> = {
  submitted: 'Submitted',
  in_progress: 'In progress',
  delivered: 'Delivered',
  accepted: 'Accepted',
  rejected: 'Rejected',
}

export function Dashboard() {
  const { isStaff, isClient } = useRoles()

  // One page of 100 is enough for the counts on this screen and keeps the
  // dashboard to a single request. The real totals live in Analytics.
  const requests = useAsync(() => api.listRequests({ page: 1 }), [])
  const episodes = useAsync(
    () => (isStaff ? api.listEpisodes({ available: true, page_size: 1 }) : Promise.resolve(null)),
    [isStaff],
  )

  if (requests.error) {
    return (
      <>
        <PageHeading title="Overview" subtitle="" />
        <ErrorBox message={requests.error} onRetry={requests.reload} />
      </>
    )
  }

  if (!requests.data) return <Loading label="Loading overview" />

  const rows: DatasetRequest[] = requests.data.results
  const total = requests.data.count
  const countOf = (status: RequestStatus) => rows.filter((row) => row.status === status).length

  return (
    <>
      <PageHeading
        title="Overview"
        subtitle={
          isStaff
            ? 'A clear view of requests and available data.'
            : 'Your dataset requests, from submission to approval.'
        }
        action={
          isClient ? (
            <Link className="btnlink" to="/requests">
              <Icon name="plus" size={14} /> New request
            </Link>
          ) : (
            <Link className="btnlink" to="/requests">
              View requests
            </Link>
          )
        }
      />

      <div className="cards">
        <MetricCard
          label="Total requests"
          value={total}
          hint={isStaff ? 'Across the workspace' : 'Your requests'}
        />
        <MetricCard
          label="In progress"
          value={countOf('in_progress')}
          hint="Being prepared by operations"
        />
        <MetricCard
          label="Awaiting review"
          value={countOf('delivered')}
          hint="Delivered to clients"
        />
        {isStaff ? (
          <MetricCard
            label="Available episodes"
            value={episodes.data ? episodes.data.count : '—'}
            hint="Good or usable, unassigned"
          />
        ) : (
          <MetricCard
            label="Accepted"
            value={countOf('accepted')}
            hint="Approved deliveries"
          />
        )}
      </div>

      <div className="split">
        <section className="panel">
          <div className="row between">
            <h2>Request pipeline</h2>
            <small>Current status</small>
          </div>
          {rows.length === 0 ? (
            <EmptyState>Nothing to show yet.</EmptyState>
          ) : (
            PIPELINE.map((status) => (
              <BarRow
                key={status}
                label={LABELS[status]}
                value={countOf(status)}
                max={rows.length}
              />
            ))
          )}
        </section>

        <section className="panel">
          <h2>{isStaff ? 'How delivery works' : 'How your request moves'}</h2>
          <ol className="muted">
            <li>A client submits their dataset needs.</li>
            <li>Operations start work and assign episodes.</li>
            <li>The client reviews the delivered metadata.</li>
            <li>The client accepts or rejects the delivery.</li>
          </ol>
          <p className="help">
            Episode metadata only. No video files are stored or served by this
            system.
          </p>
        </section>
      </div>

      <section className="panel">
        <div className="row between">
          <h2>Recent requests</h2>
          <Link className="btnlink" to="/requests">
            View all
          </Link>
        </div>
        {rows.length === 0 ? (
          <EmptyState>
            {isClient
              ? 'No requests yet. Create one from the Requests page.'
              : 'No requests have been submitted yet.'}
          </EmptyState>
        ) : (
          <RequestTable rows={rows.slice(0, 5)} showClient={isStaff} />
        )}
      </section>
    </>
  )
}
