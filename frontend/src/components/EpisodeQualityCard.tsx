/** Daily episode quality imports with business-timezone range filters. */

import { useState, type FormEvent } from 'react'

import { api } from '../api/client'
import { useAsync } from '../api/useAsync'
import { shiftDay, todayInBusinessZone } from './format'
import { ErrorBox, Loading } from './ui'
import { QualityBarChart } from './QualityBarChart'

type RangeMode = 'week' | 'month' | 'custom'
interface DateRange {
  start: string
  end: string
}

const MAX_RANGE_DAYS = 366

function weekRange(end: string): DateRange {
  const weekday = new Date(`${end}T00:00:00Z`).getUTCDay()
  return { start: shiftDay(end, -((weekday + 6) % 7)), end }
}

function monthRange(end: string): DateRange {
  return { start: `${end.slice(0, 7)}-01`, end }
}

export function EpisodeQualityCard() {
  const [mode, setMode] = useState<RangeMode>('week')
  const [range, setRange] = useState<DateRange>(() => weekRange(todayInBusinessZone()))
  const [customStart, setCustomStart] = useState(() => monthRange(todayInBusinessZone()).start)
  const [customEnd, setCustomEnd] = useState(() => todayInBusinessZone())
  const [rangeError, setRangeError] = useState('')

  const state = useAsync(
    () => api.episodeQuality(range.start, range.end),
    [range.start, range.end],
  )

  function applyCustomRange(event: FormEvent) {
    event.preventDefault()
    const span = (Date.parse(customEnd) - Date.parse(customStart)) / 86_400_000 + 1
    if (customStart > customEnd) {
      setRangeError('The start date must be on or before the end date.')
      return
    }
    if (span > MAX_RANGE_DAYS) {
      setRangeError(`Choose a range of at most ${String(MAX_RANGE_DAYS)} days.`)
      return
    }
    setRangeError('')
    setRange({ start: customStart, end: customEnd })
  }

  function chooseMode(nextMode: RangeMode) {
    setMode(nextMode)
    setRangeError('')
    const today = todayInBusinessZone()
    if (nextMode === 'week') setRange(weekRange(today))
    if (nextMode === 'month') setRange(monthRange(today))
  }

  return (
    <section className="panel quality-panel">
      <div className="row between quality-panel-head">
        <div>
          <h2>Episode quality</h2>
          <p className="sub">Daily imported episodes by quality.</p>
        </div>
        <div className="range-toggle" role="group" aria-label="Episode quality date range">
          {([
            ['week', 'This week'],
            ['month', 'This month'],
            ['custom', 'Custom'],
          ] as const).map(([option, label]) => (
        <button
          key={option}
          type="button"
          aria-pressed={mode === option}
          onClick={() => {
            chooseMode(option)
          }}
        >
          {label}
        </button>
          ))}
        </div>
      </div>

      {mode === 'custom' ? (
        <form className="quality-custom-range" onSubmit={applyCustomRange}>
          <label>
            Start date
            <input
              type="date"
              required
              max={customEnd || todayInBusinessZone()}
              value={customStart}
              onChange={(event) => {
                setCustomStart(event.target.value)
              }}
            />
          </label>
          <label>
            End date
            <input
              type="date"
              required
              min={customStart}
              max={todayInBusinessZone()}
              value={customEnd}
              onChange={(event) => {
                setCustomEnd(event.target.value)
              }}
            />
          </label>
          <button className="primary" type="submit">Apply dates</button>
        </form>
      ) : null}

      {rangeError ? <p className="error" role="alert">{rangeError}</p> : null}

      {state.error ? (
        <ErrorBox message={state.error} onRetry={state.reload} />
      ) : state.loading ? (
        <Loading label="Counting imports" />
      ) : !state.data ? null : (
        <>
          <QualityBarChart days={state.data.days} start={range.start} end={range.end} />
          <p className="qchart-note">
            {state.data.total_imported} episodes imported. Day boundaries use
            {` ${state.data.timezone}`}; only successful imports are counted.
            {state.data.data_start && state.data.data_start > range.start ? (
              <> History before {state.data.data_start} is unavailable.</>
            ) : null}
          </p>
        </>
      )}
    </section>
  )
}
