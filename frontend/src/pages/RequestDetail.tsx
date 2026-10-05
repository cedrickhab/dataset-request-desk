/**
 * Request detail: requirements, assigned episodes, status history, actions.
 *
 * Every button here is driven by `allowed_actions` from the server, never by
 * a role check in this file. When the server refuses anyway (because someone
 * else moved the request first), the 409 message is shown and the page
 * refetches, so the user sees the real current state rather than a stale one.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import { errorMessage, useAsync } from '../api/useAsync'
import type { Assignment, Episode, RequestStatus } from '../api/types'
import { useRoles } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import {
  Badge,
  EmptyState,
  ErrorBox,
  Loading,
  Modal,
  Pagination,
  PageHeading,
  QualityBadge,
  Spinner,
  StatusBadge,
  TableWrap,
  Toast,
} from '../components/ui'
import {
  exportLabel,
  formatDate,
  formatDateTime,
  statusLabel,
} from '../components/format'

/** Export states that are still moving, so the page should keep polling. */
const ACTIVE_EXPORTS = new Set(['pending', 'processing', 'retry_wait'])
const POLL_INTERVAL_MS = 3000
const PAGE_SIZE = 10

export function RequestDetail() {
  const { id = '' } = useParams()
  const { isStaff } = useRoles()
  const [toast, setToast] = useState('')
  const [actionError, setActionError] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const [assigning, setAssigning] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [assignedPageState, setAssignedPageState] = useState({ requestId: id, page: 1 })

  const request = useAsync((signal) => api.getRequest(id, signal), [id])
  const assignments = useAsync((signal) => api.listAssignments(id, signal), [id])
  const history = useAsync(() => api.getHistory(id), [id])

  const reloadAll = useCallback(() => {
    request.reload()
    assignments.reload()
    history.reload()
  }, [request, assignments, history])

  const rows = assignments.data?.results ?? []
  const hasActiveExports = rows.some(
    (row) => row.export_job && ACTIVE_EXPORTS.has(row.export_job.status),
  )
  const assignedPage = Math.min(
    assignedPageState.requestId === id ? assignedPageState.page : 1,
    Math.max(1, Math.ceil(rows.length / PAGE_SIZE)),
  )

  // Poll only while a job is actually moving, and skip the tick when the tab
  // is hidden. Polling a quiet page every 3 seconds would burn the mobile
  // data and battery of users who are paying for both.
  const reloadAssignments = assignments.reload

  useEffect(() => {
    if (!hasActiveExports) return
    let timer: number | undefined

    const tick = () => {
      if (document.visibilityState === 'visible') reloadAssignments()
      timer = window.setTimeout(tick, POLL_INTERVAL_MS)
    }
    timer = window.setTimeout(tick, POLL_INTERVAL_MS)

    return () => {
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [hasActiveExports, reloadAssignments])

  async function runTransition(status: RequestStatus, reason?: string) {
    setPending(status)
    setActionError('')
    try {
      await api.transition(id, status, reason)
      setToast(`Request marked ${statusLabel(status).toLowerCase()}.`)
      reloadAll()
    } catch (caught) {
      setActionError(errorMessage(caught, 'Could not update this request.'))
      // A conflict means our view was stale; refetch so the buttons match
      // reality before the user tries again.
      if (caught instanceof ApiError && caught.isConflict) reloadAll()
    } finally {
      setPending(null)
    }
  }

  async function removeAssignment(assignmentId: string) {
    setPending(assignmentId)
    setActionError('')
    try {
      await api.removeAssignment(id, assignmentId)
      setToast('Episode released.')
      reloadAll()
    } catch (caught) {
      setActionError(errorMessage(caught, 'Could not remove that episode.'))
      if (caught instanceof ApiError && caught.isConflict) reloadAll()
    } finally {
      setPending(null)
    }
  }

  if (request.error) {
    return (
      <>
        <PageHeading title="Request" subtitle="" action={<BackLink />} />
        <ErrorBox message={request.error} onRetry={request.reload} />
      </>
    )
  }

  if (!request.data) return <Loading label="Loading request" />

  const detail = request.data
  const actions = detail.allowed_actions
  const assignedCount = assignments.data?.assigned_count ?? detail.assigned_count
  const shortfall = detail.episodes_requested - assignedCount
  const canEditAssignments = isStaff && detail.status === 'in_progress'

  return (
    <>
      <PageHeading
        title={detail.task_name}
        subtitle={`${detail.client_name} · created ${formatDate(detail.created_at)}`}
        action={<BackLink />}
      />

      {actionError ? <ErrorBox message={actionError} /> : null}

      <div className="detailgrid">
        <div>
          <section className="panel" style={{ marginBottom: 20 }}>
            <div className="row between">
              <h2>Request details</h2>
              <StatusBadge status={detail.status} />
            </div>

            <div className="info">
              <div>
                <small>Episodes requested</small>
                <strong>{detail.episodes_requested}</strong>
              </div>
              <div>
                <small>Assigned episodes</small>
                <strong>{assignedCount}</strong>
              </div>
              <div>
                <small>Deadline</small>
                <strong>{formatDate(detail.deadline)}</strong>
              </div>
            </div>

            <p>{detail.notes || 'No additional notes.'}</p>

            <div className="row">
              {actions.includes('start_work') ? (
                <button
                  type="button"
                  className="primary"
                  disabled={pending !== null}
                  aria-busy={pending === 'in_progress'}
                  onClick={() => void runTransition('in_progress')}
                >
                  Start work
                </button>
              ) : null}

              {actions.includes('restart_work') ? (
                <button
                  type="button"
                  className="primary"
                  disabled={pending !== null}
                  aria-busy={pending === 'in_progress'}
                  onClick={() => void runTransition('in_progress')}
                >
                  <Icon name="rotate-ccw" size={15} /> Restart work
                </button>
              ) : null}

              {actions.includes('assign') ? (
                <button
                  type="button"
                  className="primary"
                  disabled={pending !== null}
                  onClick={() => {
                    setAssigning(true)
                  }}
                >
                  <Icon name="plus" size={15} /> Assign episodes
                </button>
              ) : null}

              {/* Shown but disabled while short, so the reason is visible
                  rather than the control simply being absent. */}
              {isStaff && detail.status === 'in_progress' ? (
                <button
                  type="button"
                  disabled={pending !== null || !actions.includes('deliver')}
                  aria-busy={pending === 'delivered'}
                  onClick={() => void runTransition('delivered')}
                >
                  Mark as delivered
                </button>
              ) : null}

              {actions.includes('accept') ? (
                <button
                  type="button"
                  className="primary"
                  disabled={pending !== null}
                  aria-busy={pending === 'accepted'}
                  onClick={() => void runTransition('accepted')}
                >
                  Accept delivery
                </button>
              ) : null}

              {actions.includes('reject') ? (
                <button
                  type="button"
                  className="danger"
                  disabled={pending !== null}
                  onClick={() => {
                    setRejecting(true)
                  }}
                >
                  Reject delivery
                </button>
              ) : null}
            </div>

            {isStaff && detail.status === 'in_progress' ? (
              <p className="help">
                {shortfall <= 0
                  ? 'Count requirement met. Export simulation does not gate delivery.'
                  : `Assign ${String(shortfall)} more episode(s) to enable delivery.`}
              </p>
            ) : null}
          </section>

          <section className="panel">
            <div className="row between">
              <h2>Assigned episodes</h2>
              {assignments.loading && assignments.data ? <Spinner label="Refreshing" /> : null}
            </div>

            {assignments.error ? (
              <ErrorBox message={assignments.error} onRetry={assignments.reload} />
            ) : assignments.loading && !assignments.data ? (
              <Loading label="Loading episodes" />
            ) : rows.length === 0 ? (
              <EmptyState>No episodes assigned yet.</EmptyState>
            ) : (
              <>
                <AssignedTable
                  rows={rows.slice((assignedPage - 1) * PAGE_SIZE, assignedPage * PAGE_SIZE)}
                  canEdit={canEditAssignments}
                  pending={pending}
                  onRemove={(assignmentId) => void removeAssignment(assignmentId)}
                />
                <Pagination
                  page={assignedPage}
                  count={rows.length}
                  pageSize={PAGE_SIZE}
                  onPage={(page) => setAssignedPageState({ requestId: id, page })}
                  busy={assignments.loading}
                />
              </>
            )}

            <p className="help">
              Metadata only. Export jobs simulate preparation; no video files are
              produced or downloaded.
            </p>
          </section>
        </div>

        <aside className="panel">
          <h2>Status history</h2>
          {history.error ? (
            <ErrorBox message={history.error} onRetry={history.reload} />
          ) : !history.data ? (
            <Loading label="Loading history" />
          ) : (
            <ul className="timeline">
              {[...history.data].reverse().map((entry) => (
                <li key={entry.id}>
                  <strong>{entry.actor_name}</strong>
                  <br />
                  {entry.previous_status
                    ? `${statusLabel(entry.previous_status)} → `
                    : ''}
                  {statusLabel(entry.new_status)}
                  <small>{formatDateTime(entry.created_at)}</small>
                  {entry.reason ? <small>Reason: {entry.reason}</small> : null}
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>

      {assigning ? (
        <AssignDialog
          requestId={id}
          taskName={detail.task_name}
          needed={Math.max(0, shortfall)}
          onClose={() => {
            setAssigning(false)
          }}
          onAssigned={(added) => {
            setAssigning(false)
            setToast(
              `${String(added)} episode(s) assigned. Simulated exports started.`,
            )
            reloadAll()
          }}
        />
      ) : null}

      {rejecting ? (
        <RejectDialog
          onClose={() => {
            setRejecting(false)
          }}
          onConfirm={(reason) => {
            setRejecting(false)
            void runTransition('rejected', reason)
          }}
        />
      ) : null}

      {toast ? (
        <Toast
          message={toast}
          onDismiss={() => {
            setToast('')
          }}
        />
      ) : null}
    </>
  )
}

function BackLink() {
  return (
    <Link className="btnlink" to="/requests">
      <Icon name="arrow-left" size={14} /> Back to requests
    </Link>
  )
}

function AssignedTable({
  rows,
  canEdit,
  pending,
  onRemove,
}: {
  rows: Assignment[]
  canEdit: boolean
  pending: string | null
  onRemove: (assignmentId: string) => void
}) {
  return (
    <TableWrap>
      <table>
        <thead>
          <tr>
            <th>EPISODE / ROBOT</th>
            <th>TASK</th>
            <th>QUALITY</th>
            <th>EXPORT SIMULATION</th>
            {canEdit ? (
              <th>
                <span className="sr-only">Actions</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <strong>{row.episode.episode_id}</strong>
                <small>
                  {row.episode.robot_id} · {row.episode.duration_seconds}s
                </small>
              </td>
              <td>{row.episode.task_name}</td>
              <td>
                <QualityBadge quality={row.episode.quality} />
              </td>
              <td>
                {row.export_job ? (
                  <>
                    <Badge kind={row.export_job.status}>
                      {exportLabel(row.export_job.status)}
                    </Badge>
                    <small className="attempts">
                      Attempt {row.export_job.attempts} of {row.export_job.max_attempts}
                      {row.export_job.last_error ? ` · ${row.export_job.last_error}` : ''}
                    </small>
                  </>
                ) : (
                  <small className="muted">No job</small>
                )}
              </td>
              {canEdit ? (
                <td>
                  <button
                    type="button"
                    className="danger"
                    disabled={pending !== null}
                    aria-busy={pending === row.id}
                    onClick={() => {
                      onRemove(row.id)
                    }}
                  >
                    <Icon name="trash-2" size={13} /> Remove
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  )
}

function AssignDialog({
  requestId,
  taskName,
  needed,
  onClose,
  onAssigned,
}: {
  requestId: string
  taskName: string
  needed: number
  onClose: () => void
  onAssigned: (added: number) => void
}) {
  const [search, setSearch] = useState('')
  const [quality, setQuality] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Only this request's task, only eligible and unreserved episodes. The
  // server enforces all three again on submit.
  const episodes = useAsync(
    (signal) =>
      api.listEpisodes({
        task_name: taskName,
        available: true,
        quality,
        search,
        page_size: 50,
      }).then((page) => {
        void signal
        return page
      }),
    [taskName, quality, search],
  )

  const rows = episodes.data?.results ?? []

  function toggle(episodeId: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(episodeId)) next.delete(episodeId)
      else next.add(episodeId)
      return next
    })
  }

  async function submit() {
    if (busy || selected.size === 0) return
    setBusy(true)
    setError('')
    try {
      const result = await api.assign(requestId, [...selected])
      onAssigned(result.created_ids.length)
    } catch (caught) {
      // Typically a 409: another operator took one of these between the list
      // and the submit. Refresh the list so the stale row disappears.
      setError(errorMessage(caught, 'Could not assign those episodes.'))
      setSelected(new Set())
      episodes.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Assign episodes"
      wide
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="primary"
            disabled={busy || selected.size === 0}
            aria-busy={busy}
            onClick={() => void submit()}
          >
            {busy ? (
              <Spinner label="Assigning" />
            ) : (
              `Assign ${selected.size > 0 ? String(selected.size) : ''} selected`
            )}
          </button>
        </>
      }
    >
      <p className="muted">
        Select available <strong>{taskName}</strong> recordings. Bad quality and
        already-reserved episodes are not listed.
        {needed > 0 ? ` ${String(needed)} more needed to enable delivery.` : ''}
      </p>

      <div className="tools">
        <label htmlFor="assign-search" className="sr-only">
          Search episodes
        </label>
        <input
          id="assign-search"
          placeholder="Search episode or robot"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value)
          }}
        />
        <label htmlFor="assign-quality" className="sr-only">
          Filter by quality
        </label>
        <select
          id="assign-quality"
          value={quality}
          onChange={(event) => {
            setQuality(event.target.value)
          }}
        >
          <option value="">Good and usable</option>
          <option value="good">good</option>
          <option value="usable">usable</option>
        </select>
        {episodes.loading ? <Spinner label="Searching" /> : null}
      </div>

      {error ? <ErrorBox message={error} /> : null}

      {episodes.error ? (
        <ErrorBox message={episodes.error} onRetry={episodes.reload} />
      ) : episodes.loading && !episodes.data ? (
        <Loading label="Finding episodes" />
      ) : rows.length === 0 ? (
        <EmptyState>No available episodes match this request.</EmptyState>
      ) : (
        <div className="assignscroll">
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>
                    <span className="sr-only">Select</span>
                  </th>
                  <th>EPISODE / ROBOT</th>
                  <th>RECORDED</th>
                  <th>DURATION</th>
                  <th>QUALITY</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((episode: Episode) => (
                  <tr key={episode.id}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.has(episode.id)}
                        aria-label={`Select ${episode.episode_id}`}
                        onChange={() => {
                          toggle(episode.id)
                        }}
                      />
                    </td>
                    <td>
                      <strong>{episode.episode_id}</strong>
                      <small>{episode.robot_id}</small>
                    </td>
                    <td>{formatDate(episode.recorded_at)}</td>
                    <td>{episode.duration_seconds}s</td>
                    <td>
                      <QualityBadge quality={episode.quality} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </div>
      )}

      <p className="help">
        {rows.length > 0
          ? `${String(episodes.data?.count ?? 0)} available matching episodes. `
          : ''}
        Each new assignment automatically starts a simulated export job.
      </p>
    </Modal>
  )
}

function RejectDialog({
  onClose,
  onConfirm,
}: {
  onClose: () => void
  onConfirm: (reason: string) => void
}) {
  const [reason, setReason] = useState('')
  return (
    <Modal
      title="Reject this delivery?"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => {
              onConfirm(reason)
            }}
          >
            Reject delivery
          </button>
        </>
      }
    >
      {/* Confirmed rather than immediate: rejection sends the request back to
          operations and is visible to them in the history. */}
      <p className="muted">
        Operations will be able to restart work, replace episodes and deliver
        again. Your reason is recorded in the status history.
      </p>
      <label htmlFor="reject-reason">Reason (optional)</label>
      <textarea
        id="reject-reason"
        maxLength={2000}
        placeholder="What was wrong with this delivery?"
        value={reason}
        onChange={(event) => {
          setReason(event.target.value)
        }}
      />
    </Modal>
  )
}
