/**
 * Dashboard card: "Episode quality over time".
 *
 * Staff-only surface (the endpoint enforces it; this screen is rendered only
 * for staff). The range selector picks 7/30/90 days ending today, where
 * "today" is the application's business calendar day in Africa/Kigali — the
 * same boundary the backend aggregates on, so the selector and the data can
 * never disagree about where a day ends.
 *
 * Empty states are honest: a range with no import history at all says so,
 * and a range that starts before the first import notes where history begins
 * rather than silently plotting zeros for dates that never existed.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { shiftDay, todayInBusinessZone } from './format'
import { EmptyState, ErrorBox, Loading } from './ui'
import { QualityLinesChart } from './QualityLinesChart'

const RANGES = [7, 30, 90] as const
type Range = (typeof RANGES)[number]

export function EpisodeQualityCard() {
  const [range, setRange] = useState<Range>(30)
  // Recomputed per render from the range; the key change refetches.
  const end = todayInBusinessZone()
  const start = shiftDay(end, -(range - 1))

  const state = useAsync(() => api.episodeQuality(start, end), [start, end])

  const selector = (
    <div className="range-toggle" role="group" aria-label="Chart date range">
      {RANGES.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={range === option}
          disabled={state.loading}
          onClick={() => {
            setRange(option)
          }}
        >
          {option} days
        </button>
      ))}
    </div>
  )

  return (
    <section className="panel">
      <div className="row between" style={{ alignItems: 'flex-start', gap: 12 }}>
        <div>
          <h2>Episode quality over time</h2>
          <p className="sub">Daily imported episodes by quality.</p>
        </div>
        {selector}
      </div>

      {state.error ? (
        <ErrorBox message={state.error} onRetry={state.reload} />
      ) : state.loading ? (
        <Loading label="Counting imports" />
      ) : !state.data ? null : state.data.days.length === 0 ? (
        <EmptyState>
          No episodes were imported in this range.
          <br />
          {state.data.data_start ? (
            <span className="faint">
              Import records begin {state.data.data_start}.
            </span>
          ) : (
            <Link to="/episodes">Import episodes to see daily quality here.</Link>
          )}
        </EmptyState>
      ) : (
        <>
          <QualityLinesChart key={`${start}/${end}`} days={state.data.days} />
          {state.data.total_imported === 0 ? (
            <p className="qchart-note">No episodes were imported in this range.</p>
          ) : null}
          <p className="qchart-note">
            Day boundaries are Africa/Kigali; counts are episodes successfully
            imported (duplicates and rejected rows are never counted).
            {state.data.data_start && state.data.data_start > start ? (
              <> History before {state.data.data_start} is unavailable.</>
            ) : null}
          </p>
        </>
      )}
    </section>
  )
}
