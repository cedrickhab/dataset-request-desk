/**
 * Analytics. Every number comes from the server's aggregate response; nothing
 * is recomputed here, so the page cannot disagree with the database.
 *
 * The date semantics the server applies are rendered verbatim from the
 * response, which keeps this screen honest about what it is showing.
 */

import { useState, type FormEvent } from 'react'

import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import type { RequestStatus } from '../api/types'
import {
  BarRow,
  EmptyState,
  ErrorBox,
  Loading,
  MetricCard,
  PageHeading,
  StatusBadge,
  TableWrap,
} from '../components/ui'
import {
  formatDuration,
  isoDay,
} from '../components/format'

const STATUSES: RequestStatus[] = [
  'submitted',
  'in_progress',
  'delivered',
  'accepted',
  'rejected',
]

function defaultRange(): { start: string; end: string } {
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - 30)
  return { start: isoDay(start), end: isoDay(end) }
}

export function Analytics() {
  const initial = defaultRange()
  // Draft values live in the inputs; `applied` is what has been requested, so
  // typing a date does not fire a query per keystroke.
  const [draft, setDraft] = useState(initial)
  const [applied, setApplied] = useState(initial)

  const state = useAsync(
    () => api.analytics(applied.start, applied.end),
    [applied.start, applied.end],
  )

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    setApplied(draft)
  }

  const report = state.data
  const topCount = report?.top_good_tasks[0]?.count ?? 0

  return (
    <>
      <PageHeading
        title="Analytics"
        subtitle="Aggregated in PostgreSQL over an inclusive UTC date range."
      />

      <section className="panel">
        <form className="tools" onSubmit={onSubmit}>
          <div>
            <label htmlFor="start">Start date (UTC)</label>
            <input
              id="start"
              type="date"
              required
              value={draft.start}
              onChange={(event) => {
                setDraft({ ...draft, start: event.target.value })
              }}
            />
          </div>
          <div>
            <label htmlFor="end">End date (UTC)</label>
            <input
              id="end"
              type="date"
              required
              value={draft.end}
              onChange={(event) => {
                setDraft({ ...draft, end: event.target.value })
              }}
            />
          </div>
          <button className="primary" style={{ alignSelf: 'end' }} type="submit">
            Apply date range
          </button>
        </form>

        {report ? (
          <p className="help">
            Episodes: {report.semantics.daily_episodes}. Request counts:{' '}
            {report.semantics.request_counts}. Median:{' '}
            {report.semantics.median_delivery_seconds}.
          </p>
        ) : null}
      </section>

      {state.error ? (
        <ErrorBox
          title="Could not load analytics"
          message={state.error}
          onRetry={state.reload}
        />
      ) : state.loading && !report ? (
        <Loading label="Aggregating" />
      ) : !report ? null : (
        <div style={{ marginTop: 20 }}>
          <div className="cards">
            <MetricCard
              label="Episodes recorded"
              value={report.totals.episodes_recorded}
            />
            <MetricCard label="Requests created" value={report.totals.requests_created} />
            <MetricCard
              label="Median time to delivery"
              value={formatDuration(report.median_delivery_seconds)}
              hint={
                report.median_delivery_seconds === null
                  ? 'No first deliveries in range'
                  : undefined
              }
            />
            <MetricCard label="Good episodes" value={report.totals.good_episodes} />
          </div>

          <div className="split">
            <section className="panel">
              <h2>Top 5 tasks · good episodes</h2>
              {report.top_good_tasks.length === 0 ? (
                <p className="muted">No good episodes in this range.</p>
              ) : (
                report.top_good_tasks.map((row) => (
                  <BarRow
                    key={row.task_name}
                    label={row.task_name}
                    value={row.count}
                    max={topCount}
                  />
                ))
              )}
            </section>

            <section className="panel">
              <h2>Requests by current status</h2>
              {STATUSES.map((status) => (
                <div className="row between" key={status} style={{ margin: '12px 0' }}>
                  <StatusBadge status={status} />
                  <strong>{report.request_counts[status]}</strong>
                </div>
              ))}
            </section>
          </div>

          <section className="panel">
            <h2>Episodes per day, per robot</h2>
            {report.daily_episodes.length === 0 ? (
              <EmptyState>No episodes were recorded in this range.</EmptyState>
            ) : (
              <TableWrap>
                <table>
                  <thead>
                    <tr>
                      <th>DAY (UTC)</th>
                      <th>ROBOT</th>
                      <th>EPISODES</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.daily_episodes.map((row) => (
                      <tr key={`${row.day}-${row.robot_id}`}>
                        <td>{row.day}</td>
                        <td>{row.robot_id}</td>
                        <td>{row.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableWrap>
            )}
            <p className="help">
              Grouped with date_trunc and COUNT in the database. The median uses
              percentile_cont; no rows are loaded into application memory to
              compute these.
            </p>
          </section>
        </div>
      )}
    </>
  )
}
