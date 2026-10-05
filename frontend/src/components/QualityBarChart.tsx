import type { QualityDay } from '../api/types'

const SERIES = [
  { key: 'good', label: 'Good', color: '#4DCD87' },
  { key: 'usable', label: 'Usable', color: '#3B92F6' },
  { key: 'bad', label: 'Bad', color: '#F46676' },
] as const

const HEIGHT = 190
const MARGIN = { top: 10, right: 14, bottom: 30, left: 38 }

function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })
}

function dateRange(start: string, end: string): string[] {
  const dates: string[] = []
  const cursor = new Date(`${start}T00:00:00Z`)
  const last = new Date(`${end}T00:00:00Z`)
  while (cursor <= last) {
    dates.push(cursor.toISOString().slice(0, 10))
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return dates
}

export function QualityBarChart({
  days,
  start,
  end,
}: {
  days: QualityDay[]
  start: string
  end: string
}) {
  const dates = days.length ? days.map((day) => day.date) : dateRange(start, end)
  const values = new Map(days.map((day) => [day.date, day]))
  const maxValue = Math.max(0, ...days.flatMap((day) => SERIES.map((series) => day[series.key])))
  const yMax = Math.max(4, Math.ceil(maxValue / 4) * 4)
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const plotWidth = Math.max(490, dates.length * 36)
  const width = MARGIN.left + plotWidth + MARGIN.right
  const bottom = MARGIN.top + plotHeight
  const step = dates.length ? plotWidth / dates.length : plotWidth
  const groupWidth = Math.min(step * 0.92, 44)
  const barWidth = Math.max(1, (groupWidth - 4) / SERIES.length)
  const labelEvery = Math.max(1, Math.ceil(dates.length / 8))

  return (
    <div className="quality-chart-scroll" tabIndex={0} aria-label="Scrollable episode quality chart">
      <svg
        className="quality-chart"
        role="img"
        aria-label={`Daily Good, Usable, and Bad episode counts from ${start} to ${end}`}
        viewBox={`0 0 ${String(width)} ${String(HEIGHT)}`}
        width={width}
        height={HEIGHT}
      >
        {[0, 1, 2, 3, 4].map((tick) => {
          const value = (tick / 4) * yMax
          const y = bottom - (value / yMax) * plotHeight
          return (
            <g key={tick}>
              <line
                className={tick === 0 ? 'quality-axis-line' : 'quality-grid-line'}
                x1={MARGIN.left}
                x2={width - MARGIN.right}
                y1={y}
                y2={y}
              />
              <text className="quality-axis-label" x={MARGIN.left - 7} y={y + 3} textAnchor="end">
                {value}
              </text>
            </g>
          )
        })}
        <line
          className="quality-axis-line"
          x1={MARGIN.left}
          x2={MARGIN.left}
          y1={MARGIN.top}
          y2={bottom}
        />
        {dates.map((date, dateIndex) => {
          const day = values.get(date)
          const center = MARGIN.left + step * (dateIndex + 0.5)
          const firstBarX = center - groupWidth / 2
          return (
            <g key={date}>
              {SERIES.map((series, seriesIndex) => {
                if (!day) return null
                const count = day?.[series.key] ?? 0
                const barHeight = (count / yMax) * plotHeight
                return (
                  <rect
                    key={series.key}
                    className="quality-column"
                    x={firstBarX + seriesIndex * (barWidth + 2)}
                    y={bottom - barHeight}
                    width={barWidth}
                    height={barHeight}
                    fill={series.color}
                    aria-label={`${shortDate(date)} ${series.label}: ${String(count)}`}
                  >
                    <title>{`${date} · ${series.label}: ${String(count)}`}</title>
                  </rect>
                )
              })}
              {dateIndex % labelEvery === 0 || dateIndex === dates.length - 1 ? (
                <text
                  className="quality-axis-label"
                  x={center}
                  y={HEIGHT - 8}
                  textAnchor="middle"
                >
                  {shortDate(date)}
                </text>
              ) : null}
            </g>
          )
        })}
      </svg>
      <ul className="quality-chart-legend" aria-label="Episode quality series">
        {SERIES.map((series) => (
          <li key={series.key}>
            <span style={{ background: series.color }} />
            {series.label}
          </li>
        ))}
      </ul>
      <div className="sr-only">
        <table>
          <caption>Daily imported episode quality counts</caption>
          <thead>
            <tr><th scope="col">Date</th><th scope="col">Good</th><th scope="col">Usable</th><th scope="col">Bad</th></tr>
          </thead>
          <tbody>
            {days.map((day) => (
              <tr key={day.date}>
                <th scope="row">{day.date}</th>
                <td>{day.good}</td><td>{day.usable}</td><td>{day.bad}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
