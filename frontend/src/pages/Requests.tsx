/**
 * Request list. One component for both audiences: staff see every request
 * plus a client column, a client sees only their own because the server
 * filters the queryset, not because this file hides rows.
 */

import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { api, ApiError } from '../api/client'
import { errorMessage, useAsync } from '../api/useAsync'
import type { DatasetRequest, RequestStatus } from '../api/types'
import { useRoles } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import {
  EmptyState,
  ErrorBox,
  Loading,
  Modal,
  PageHeading,
  Pagination,
  Spinner,
  StatusBadge,
  TableWrap,
  Toast,
} from '../components/ui'
import {
  formatDate,
  isoDay,
} from '../components/format'

const PAGE_SIZE = 10

const STATUSES: RequestStatus[] = [
  'submitted',
  'in_progress',
  'delivered',
  'accepted',
  'rejected',
]

export function Requests() {
  const { isStaff, isClient } = useRoles()
  const [searchParams] = useSearchParams()
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState(() => searchParams.get('status') ?? '')
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [toast, setToast] = useState('')

  const state = useAsync(
    () => api.listRequests({ page, page_size: PAGE_SIZE, status, search }),
    [page, status, search],
  )

  return (
    <>
      <PageHeading
        title={isStaff ? 'Requests' : 'My requests'}
        subtitle="Track requirements, allocation and client decisions."
        action={
          isClient ? (
            <button
              type="button"
              className="primary"
              onClick={() => {
                setCreating(true)
              }}
            >
              <Icon name="plus" size={15} /> New request
            </button>
          ) : undefined
        }
      />

      <section className="panel">
        <div className="tools">
          <label htmlFor="request-search" className="sr-only">
            Search requests
          </label>
          <input
            id="request-search"
            placeholder="Search by task name"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setPage(1)
            }}
          />
          <label htmlFor="request-status" className="sr-only">
            Filter by status
          </label>
          <select
            id="request-status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value)
              setPage(1)
            }}
          >
            <option value="">All statuses</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {value === 'in_progress'
                  ? 'In progress'
                  : value.charAt(0).toUpperCase() + value.slice(1)}
              </option>
            ))}
          </select>
          {state.loading && state.data ? <Spinner label="Updating" /> : null}
        </div>

        {state.error ? (
          <ErrorBox message={state.error} onRetry={state.reload} />
        ) : state.loading && !state.data ? (
          <Loading label="Loading requests" />
        ) : !state.data || state.data.results.length === 0 ? (
          <EmptyState>
            {search || status
              ? 'No requests match these filters. Clear them to see everything.'
              : isClient
                ? 'No requests yet. Create one to get started.'
                : 'No requests have been submitted yet.'}
          </EmptyState>
        ) : (
          <>
            <RequestTable rows={state.data.results} showClient={isStaff} />
            <Pagination
              page={page}
              count={state.data.count}
              pageSize={PAGE_SIZE}
              onPage={setPage}
              busy={state.loading}
            />
          </>
        )}
      </section>

      {creating ? (
        <NewRequestDialog
          onClose={() => {
            setCreating(false)
          }}
          onCreated={(created) => {
            setCreating(false)
            setToast('Request submitted.')
            setPage(1)
            state.reload()
            return created
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

export function RequestTable({
  rows,
  showClient,
}: {
  rows: DatasetRequest[]
  showClient: boolean
}) {
  return (
    <TableWrap>
      <table>
        <thead>
          <tr>
            <th>REQUEST / TASK</th>
            {showClient ? <th>CLIENT</th> : null}
            <th>ASSIGNED</th>
            <th>DEADLINE</th>
            <th>STATUS</th>
            <th>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <strong>{row.task_name}</strong>
                <small>{row.episodes_requested} episode(s) requested</small>
              </td>
              {showClient ? <td>{row.client_name}</td> : null}
              <td>
                {row.assigned_count} / {row.episodes_requested}
              </td>
              <td>{formatDate(row.deadline)}</td>
              <td>
                <StatusBadge status={row.status} />
              </td>
              <td>
                <Link className="btnlink table-open" to={`/requests/${row.id}`}>
                  Open
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  )
}

const COMMON_TASKS = [
  'pick cup',
  'fold towel',
  'open drawer',
  'stack blocks',
  'wipe table',
  'pour water',
  'place cup on shelf',
]

function NewRequestDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (created: DatasetRequest) => void
}) {
  const navigate = useNavigate()
  const [taskName, setTaskName] = useState('')
  const [count, setCount] = useState('2')
  const [deadline, setDeadline] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})

  // Only a `min` attribute, to make the picker helpful. The server is the
  // authority and validates the deadline against the Kigali calendar date.
  const minDate = useMemo(() => isoDay(new Date()), [])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setFields({})
    try {
      const created = await api.createRequest({
        task_name: taskName,
        episodes_requested: Number(count),
        deadline,
        notes,
      })
      onCreated(created)
      void navigate(`/requests/${created.id}`)
    } catch (caught) {
      if (caught instanceof ApiError && Object.keys(caught.fields).length > 0) {
        // Surface server-side field errors inline, next to the input that
        // caused them, rather than as one opaque banner.
        const mapped: Record<string, string> = {}
        for (const [key, messages] of Object.entries(caught.fields)) {
          if (messages[0]) mapped[key] = messages[0]
        }
        setFields(mapped)
        setError('Check the highlighted fields.')
      } else {
        setError(errorMessage(caught, 'Could not submit this request.'))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Create dataset request"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="submit"
            form="new-request"
            className="primary"
            disabled={busy}
            aria-busy={busy}
          >
            {busy ? <Spinner label="Submitting" /> : 'Submit request'}
          </button>
        </>
      }
    >
      <form id="new-request" onSubmit={onSubmit} noValidate>
        <label htmlFor="task">Task name</label>
        <input
          id="task"
          list="common-tasks"
          required
          maxLength={120}
          placeholder="e.g. pick cup"
          value={taskName}
          aria-invalid={fields.task_name ? true : undefined}
          onChange={(event) => {
            setTaskName(event.target.value)
          }}
        />
        <datalist id="common-tasks">
          {COMMON_TASKS.map((task) => (
            <option key={task} value={task} />
          ))}
        </datalist>
        {fields.task_name ? <p className="fielderror">{fields.task_name}</p> : null}

        <div className="formgrid">
          <div>
            <label htmlFor="count">Episodes requested</label>
            <input
              id="count"
              type="number"
              min={1}
              max={100000}
              required
              value={count}
              aria-invalid={fields.episodes_requested ? true : undefined}
              onChange={(event) => {
                setCount(event.target.value)
              }}
            />
            {fields.episodes_requested ? (
              <p className="fielderror">{fields.episodes_requested}</p>
            ) : null}
          </div>
          <div>
            <label htmlFor="deadline">Deadline</label>
            <input
              id="deadline"
              type="date"
              min={minDate}
              required
              value={deadline}
              aria-invalid={fields.deadline ? true : undefined}
              onChange={(event) => {
                setDeadline(event.target.value)
              }}
            />
            {fields.deadline ? <p className="fielderror">{fields.deadline}</p> : null}
          </div>
        </div>

        <label htmlFor="notes">Notes</label>
        <textarea
          id="notes"
          maxLength={4000}
          placeholder="Describe any additional requirements"
          value={notes}
          onChange={(event) => {
            setNotes(event.target.value)
          }}
        />

        <p className="help">
          Your request starts as Submitted. Staff will select suitable episodes.
        </p>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  )
}

