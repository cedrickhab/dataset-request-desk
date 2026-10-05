/**
 * Episode quality over time: three thin lines (Good/Usable/Bad) of episodes
 * successfully imported per business day.
 *
 * Rendering is plain SVG — the app carries no chart library, and a hand-rolled
 * plot of three series stays well under the weight of any dependency, which
 * matters on the metered connections this app is built for.
 *
 * Interaction contract:
 *  - one fine vertical dashed crosshair at the selected date, with small
 *    coloured circles where the three series cross it;
 *  - one compact dark tooltip with date, per-quality counts and the total,
 *    clamped inside the visible chart area, values right-aligned;
 *  - pointer (mouse or touch) and keyboard (focus + arrow keys) reach the same
 *    state; no stored data changes and nothing outside the plot reflows;
 *  - a screen-reader summary that follows the selection plus a visually
 *    hidden data table carry the same numbers as the pixels.
 *
 * Curves are monotone (Fritsch-Carlson): they pass through every point and,
 * because y starts at zero and monotone tangents never overshoot local data,
 * can never dip below zero. A single date renders honest points with no
 * invented line.
 */

import { useEffect, useMemo, useRef, useState } from 'react'

import type { QualityDay } from '../api/types'

const SERIES: { key: keyof Omit<QualityDay, 'date'>; label: string; color: string }[] = [
  { key: 'good', label: 'Good', color: '#4DCD87' },
  { key: 'usable', label: 'Usable', color: '#3B92F6' },
  { key: 'bad', label: 'Bad', color: '#F46676' },
]

const PLOT_HEIGHT = 232
const MARGIN = { top: 12, right: 14, bottom: 26, left: 40 }
const TOOLTIP_WIDTH = 190
const CROSSHAIR = '#5B6B80'

/** Fritsch–Carlson monotone cubic through every point, no overshoot. */
function monotonePath(points: { x: number; y: number }[]): string {
  if (points.length < 2) return ''
  const n = points.length
  const dx: number[] = []
  const slope: number[] = []
  for (let i = 0; i < n - 1; i += 1) {
    const a = points[i]!
    const b = points[i + 1]!
    dx.push(b.x - a.x)
    slope.push((b.y - a.y) / Math.max(b.x - a.x, Number.EPSILON))
  }
  const tangent: number[] = [slope[0]!]
  for (let i = 1; i < n - 1; i += 1) {
    if (slope[i - 1]! * slope[i]! <= 0) {
      tangent.push(0)
    } else {
      const w1 = 2 * dx[i]! + dx[i - 1]!
      const w2 = dx[i]! + 2 * dx[i - 1]!
      tangent.push((w1 + w2) / (w1 / slope[i - 1]! + w2 / slope[i]!))
    }
  }
  tangent.push(slope[n - 2]!)

  let path = `M ${points[0]!.x.toFixed(2)} ${points[0]!.y.toFixed(2)}`
  for (let i = 0; i < n - 1; i += 1) {
    const a = points[i]!
    const b = points[i + 1]!
    const h = dx[i]! / 3
    path += ` C ${(a.x + h).toFixed(2)} ${(a.y + tangent[i]! * h).toFixed(2)},` +
      ` ${(b.x - h).toFixed(2)} ${(b.y - tangent[i + 1]! * h).toFixed(2)},` +
      ` ${b.x.toFixed(2)} ${b.y.toFixed(2)}`
  }
  return path
}

/** Smallest "nice" ceiling of value from 1/2/2.5/5 × 10^k, always ≥ 1. */
function niceCeiling(value: number): number {
  if (value <= 1) return 1
  const power = Math.floor(Math.log10(value))
  const base = Math.pow(10, power)
  for (const step of [1, 2, 2.5, 5, 10]) {
    if (step * base >= value) return step * base
  }
  return 10 * base
}

function dayLabel(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })
}

function longDayLabel(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function QualityLinesChart({ days }: { days: QualityDay[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) setWidth(Math.max(0, entry.contentRect.width))
    })
    observer.observe(element)
    return () => {
      observer.disconnect()
    }
  }, [])

  // jsdom reports zero-size rects; a nominal width keeps the chart renderable
  // in tests and in the instant before the first measurement lands.
  const svgWidth = width > 40 ? width : 560

  const count = days.length
  const innerWidth = Math.max(10, svgWidth - MARGIN.left - MARGIN.right)
  const innerHeight = PLOT_HEIGHT - MARGIN.top - MARGIN.bottom

  const { yMax, paths, points, xAt, yFor, step } = useMemo(() => {
    const observed = Math.max(
      0,
      ...days.map((day) => Math.max(day.good, day.usable, day.bad)),
    )
    // All-zero data still gets a nonzero axis so a flat line reads as "zero",
    // not as a broken chart; and the scale is never zero, so no divide by zero.
    const yMaxLocal = niceCeiling(observed === 0 ? 4 : observed)
    const innerHeightLocal = PLOT_HEIGHT - MARGIN.top - MARGIN.bottom
    const stepLocal = count > 1 ? innerWidth / (count - 1) : 0
    const xAtLocal = (index: number): number =>
      count === 1 ? MARGIN.left + innerWidth / 2 : MARGIN.left + index * stepLocal
    const yAtLocal = (value: number): number =>
      MARGIN.top + innerHeightLocal - (Math.max(0, value) / yMaxLocal) * innerHeightLocal

    const perSeries = SERIES.map(({ key }) =>
      days.map((day, index) => ({ x: xAtLocal(index), y: yAtLocal(day[key]) })),
    )
    return {
      yMax: yMaxLocal,
      paths: perSeries.map((pts) => monotonePath(pts)),
      points: perSeries,
      xAt: xAtLocal,
      yFor: yAtLocal,
      step: stepLocal,
    }
  }, [days, count, innerWidth])

  const gridStep = Math.max(1, Math.ceil(yMax / 4))
  const gridValues = Array.from({ length: Math.floor(yMax / gridStep) + 1 }, (_, i) => i * gridStep)

  // Roughly six date labels regardless of range length; the last date is
  // always labelled so the range's end is anchored.
  const labelEvery = Math.max(1, Math.ceil((count - 1) / Math.max(1, Math.floor(innerWidth / 70))))
  const active = activeIndex !== null ? days[activeIndex] : undefined

  function selectNearest(clientX: number, target: Element) {
    if (count === 0) return
    const rect = target.getBoundingClientRect()
    const x = (clientX - rect.left) * (rect.width > 0 ? svgWidth / rect.width : 1)
    if (count === 1) {
      setActiveIndex(0)
      return
    }
    const raw = (x - MARGIN.left) / Math.max(step, Number.EPSILON)
    setActiveIndex(Math.min(count - 1, Math.max(0, Math.round(raw))))
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (count === 0) return
    const last = count - 1
    const jump = (next: number) => {
      event.preventDefault()
      setActiveIndex(Math.min(last, Math.max(0, next)))
    }
    if (event.key === 'ArrowRight') {
      jump(activeIndex === null ? last : activeIndex + 1)
    } else if (event.key === 'ArrowLeft') {
      jump(activeIndex === null ? last : activeIndex - 1)
    } else if (event.key === 'Home') {
      jump(0)
    } else if (event.key === 'End') {
      jump(last)
    } else if (event.key === 'Escape') {
      setActiveIndex(null)
    }
  }

  const total = (day: QualityDay): number => day.good + day.usable + day.bad
  const latest = count > 0 ? days[count - 1] : undefined

  // Tooltip position: follow the crosshair horizontally, clamped so it always
  // stays inside the visible chart area; fixed vertical band, so the card
  // height never changes when it appears.
  const tooltipLeft =
    activeIndex !== null
      ? Math.min(
          Math.max(xAt(activeIndex) - TOOLTIP_WIDTH / 2, 4),
          Math.max(4, svgWidth - TOOLTIP_WIDTH - 4),
        )
      : 0

  return (
    <div>
      <div className="qlegend" aria-hidden="true">
        {SERIES.map(({ key, label, color }) => (
          <span className="key" key={key}>
            <span className="qdot" style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>

      <div
        ref={containerRef}
        className="qchart"
        tabIndex={0}
        role="group"
        aria-label={
          'Episode quality over time. Use the left and right arrow keys to step through dates.'
        }
        onKeyDown={onKeyDown}
        onBlur={() => setActiveIndex(null)}
        onFocus={() => {
          if (activeIndex === null && count > 0) setActiveIndex(count - 1)
        }}
        style={{ touchAction: 'pan-y' }}
      >
        <svg
          width={svgWidth}
          height={PLOT_HEIGHT}
          viewBox={`0 0 ${svgWidth} ${PLOT_HEIGHT}`}
          role="img"
          aria-hidden="true"
          onPointerMove={(event) => {
            selectNearest(event.clientX, event.currentTarget)
          }}
          onPointerDown={(event) => {
            selectNearest(event.clientX, event.currentTarget)
          }}
          onPointerLeave={(event) => {
            // Touch emits pointerleave when the finger lifts. Keep that
            // selection visible so the user can read the shared counts.
            if (event.pointerType !== 'touch') setActiveIndex(null)
          }}
          style={{ display: 'block' }}
        >
          {gridValues.map((value) => (
            <g key={value}>
              <line
                x1={MARGIN.left}
                x2={svgWidth - MARGIN.right}
                y1={yFor(value)}
                y2={yFor(value)}
                stroke="#232B37"
                strokeDasharray="3 4"
                strokeWidth={1}
              />
              <text
                x={MARGIN.left - 8}
                y={yFor(value) + 3.5}
                textAnchor="end"
                fontSize={10}
                fill="#8996AA"
              >
                {Math.round(value)}
              </text>
            </g>
          ))}

          {days.map((day, index) =>
            (index % labelEvery === 0 && count - 1 - index >= labelEvery) || index === count - 1 ? (
              <text
                key={day.date}
                x={xAt(index)}
                y={PLOT_HEIGHT - 7}
                textAnchor="middle"
                fontSize={10}
                fill="#8996AA"
              >
                {dayLabel(day.date)}
              </text>
            ) : null,
          )}

          {activeIndex !== null ? (
            <line
              x1={xAt(activeIndex)}
              x2={xAt(activeIndex)}
              y1={MARGIN.top}
              y2={MARGIN.top + innerHeight}
              stroke={CROSSHAIR}
              strokeDasharray="2 3"
              strokeWidth={1}
            />
          ) : null}

          {count === 1
            ? SERIES.map(({ key, color }, seriesIndex) => (
                <circle
                  key={key}
                  cx={points[seriesIndex]?.[0]?.x}
                  cy={points[seriesIndex]?.[0]?.y}
                  r={3.5}
                  fill={color}
                  stroke="#141A22"
                  strokeWidth={1.5}
                />
              ))
            : SERIES.map(({ key, color }, seriesIndex) => (
                <path
                  key={key}
                  d={paths[seriesIndex]}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              ))}

          {activeIndex !== null
            ? SERIES.map(({ key, color }, seriesIndex) => (
                <circle
                  key={key}
                  cx={points[seriesIndex]?.[activeIndex]?.x}
                  cy={points[seriesIndex]?.[activeIndex]?.y}
                  r={3.5}
                  fill={color}
                  stroke="#141A22"
                  strokeWidth={1.5}
                />
              ))
            : null}
        </svg>

        {active ? (
          <div
            className="qtooltip"
            style={{ left: tooltipLeft, top: MARGIN.top + 4, width: TOOLTIP_WIDTH }}
          >
            <div className="qtitle">{longDayLabel(active.date)}</div>
            {SERIES.map(({ key, label, color }) => (
              <div className="qrow" key={key}>
                <span>
                  <span className="qdot" style={{ background: color }} /> {label}
                </span>
                <b>{active[key]}</b>
              </div>
            ))}
            <div className="qrow">
              <span>Total</span>
              <b>{total(active)}</b>
            </div>
          </div>
        ) : null}
      </div>

      {/* The selection, spoken as it changes. */}
      <p className="sr-only" aria-live="polite">
        {active
          ? `${longDayLabel(active.date)}: Good ${active.good}, Usable ${active.usable}, Bad ${active.bad}, Total ${total(active)}.`
          : latest
            ? `Chart of ${count} day${count === 1 ? '' : 's'} of imports. Latest ${longDayLabel(latest.date)}: Total ${total(latest)}.`
            : 'No import data.'}
      </p>

      {/* Equivalent data table for screen readers and no-hover contexts. */}
      <div className="sr-only">
      <table>
        <caption>Daily imported episodes by quality</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Good</th>
            <th scope="col">Usable</th>
            <th scope="col">Bad</th>
            <th scope="col">Total</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <th scope="row">{day.date}</th>
              <td>{day.good}</td>
              <td>{day.usable}</td>
              <td>{day.bad}</td>
              <td>{total(day)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  )
}
