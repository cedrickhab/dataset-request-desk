/**
 * Overview.
 *
 * Counts here are derived from the request list the viewer can already see,
 * so a client's dashboard is scoped by the same server-side filter as their
 * list. The episode-quality chart calls the staff-only quality-series
 * endpoint and is rendered for staff only: a client's dashboard stays inside
 * their own permissions.
 */

import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import type { DatasetRequest, RequestStatus } from '../api/types'
import { useRoles } from '../auth/useAuth'
import { EpisodeQualityCard } from '../components/EpisodeQualityCard'
import { QualityDonut } from '../components/QualityDonut'
import { Icon, type IconName } from '../components/Icon'
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

// Semantic status colours of the approved design. Amber is never used here:
// it is reserved for branding, primary actions and selected navigation.
const PIPELINE_COLORS: Record<RequestStatus, string> = {
  submitted: '#8996AA',
  in_progress: '#3B92F6',
  delivered: '#37C9E6',
  accepted: '#4DCD87',
  rejected: '#F46676',
}

export function Dashboard() {
  const { isStaff, isClient } = useRoles()

  // Count filtered, server-scoped lists, not just statuses on the first page.
  const requests = useAsync(async () => {
    const [recent, ...counts] = await Promise.all([
      api.listRequests({ page: 1 }),
      ...PIPELINE.map((status) => api.listRequests({ status, page_size: 1 })),
    ])
    return { ...recent, statusCounts: Object.fromEntries(
      PIPELINE.map((status, index) => [status, counts[index]?.count ?? 0]),
    ) }
  }, [])
  const episodes = useAsync(
    () =>
      isStaff
        ? Promise.all([
            api.listEpisodes({ page_size: 1 }),
            api.listEpisodes({ available: true, page_size: 1 }),
            api.listEpisodes({ quality: 'bad', page_size: 1 }),
            api.listEpisodes({ quality: 'good', page_size: 1 }),
            api.listEpisodes({ quality: 'usable', page_size: 1 }),
          ])
        : Promise.resolve(null),
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
  const countOf = (status: RequestStatus) => requests.data?.statusCounts[status] ?? 0

  // One common scale for the pipeline rows: relative to the largest current
  // count, never the total, so a single dominant status cannot flatten the
  // others into invisibility. Zero-count rows stay listed.
  const largest = Math.max(1, ...PIPELINE.map((status) => countOf(status)))

  const inventory = episodes.data
  // Exact derivation from three real server counts: every episode is either
  // reserved (only good/usable can be), available (unreserved, assignable) or
  // an unreserved bad-quality row, so reserved = total - available - bad.
  const totalEpisodes = inventory ? inventory[0].count : null
  const allocatedEpisodes =
    inventory && totalEpisodes !== null
      ? Math.max(0, totalEpisodes - inventory[1].count - inventory[2].count)
      : null

  // Donut slices come from real per-quality server counts, never from the
  // derived allocation figures above.
  const qualityCounts = inventory
    ? { good: inventory[3]?.count ?? 0, usable: inventory[4]?.count ?? 0, bad: inventory[2]?.count ?? 0 }
    : { good: 0, usable: 0, bad: 0 }

  const staffCards: { label: string; value: React.ReactNode; hint: string; icon: IconName }[] =
    [
      {
        label: 'Episodes',
        value: totalEpisodes ?? '—',
        hint: 'In the inventory',
        icon: 'database',
      },
      {
        label: 'Requests',
        value: total,
        hint: 'Across the workspace',
        icon: 'clipboard-list',
      },
      {
        label: 'Allocated',
        value: allocatedEpisodes ?? '—',
        hint: 'Reserved for requests',
        icon: 'layers',
      },
      {
        label: 'Delivered',
        value: countOf('delivered'),
        hint: 'Awaiting client review',
        icon: 'package-check',
      },
    ]

  const clientCards: { label: string; value: React.ReactNode; hint: string; icon: IconName }[] =
    [
      { label: 'Requests', value: total, hint: 'Your requests', icon: 'clipboard-list' },
      {
        label: 'In progress',
        value: countOf('in_progress'),
        hint: 'Being prepared by operations',
        icon: 'clock',
      },
      {
        label: 'Awaiting review',
        value: countOf('delivered'),
        hint: 'Delivered to you',
        icon: 'package-check',
      },
      {
        label: 'Accepted',
        value: countOf('accepted'),
        hint: 'Approved deliveries',
        icon: 'circle-check',
      },
    ]

  const cards = isStaff ? staffCards : clientCards

  return (
    <>
      <PageHeading
        title="Overview"
        subtitle={
          isStaff
            ? 'Workspace activity at a glance.'
            : 'Your dataset requests, from submission to approval.'
        }
        action={
          <Link className="btnlink primary" to="/requests">
            {isClient ? (
              <>
                <Icon name="plus" size={14} /> New request
              </>
            ) : (
              'View requests'
            )}
          </Link>
        }
      />

      <div className="cards">
        {cards.map((card) => (
          <MetricCard
            key={card.label}
            label={card.label}
            value={card.value}
            hint={card.hint}
            icon={card.icon}
          />
        ))}
      </div>

      <div className="split">
        <section className="panel">
          <h2>Request pipeline</h2>
          <p className="sub">Current status of dataset requests.</p>
          {total === 0 ? (
            <EmptyState>
              {isClient ? (
                <Link to="/requests">Create your first request</Link>
              ) : (
                <Link to="/episodes">Import episodes to prepare for client requests</Link>
              )}
            </EmptyState>
          ) : (
            PIPELINE.map((status) => (
              <BarRow
                key={status}
                label={LABELS[status]}
                value={countOf(status)}
                max={largest}
                color={PIPELINE_COLORS[status]}
              />
            ))
          )}
        </section>

        <section className="panel">
          <h2>{isStaff ? 'Episode quality' : 'How your request moves'}</h2>
          {isStaff ? (
            <>
              <p className="sub">Imported episodes by quality.</p>
              <QualityDonut counts={qualityCounts} />
            </>
          ) : (
            <>
              <ol className="muted">
                <li>Submit your dataset needs.</li>
                <li>Staff start work and assign episodes.</li>
                <li>Review the delivered metadata.</li>
                <li>Accept or reject the delivery.</li>
              </ol>
              <p className="help">
                Episode metadata only. No video files are stored or served by
                this system.
              </p>
            </>
          )}
        </section>
      </div>

      {isStaff ? <EpisodeQualityCard /> : null}

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
