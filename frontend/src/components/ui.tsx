/**
 * Shared presentational pieces.
 *
 * Deliberately small and shared rather than re-declared per page: the badge,
 * table wrapper, pager and dialog each appear on several screens, and the
 * prototype's density only stays consistent if there is one of each.
 */

import {
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from 'react'

import { Icon } from './Icon'
import { statusLabel, titleCase, type BadgeKind } from './format'
import type { Quality, RequestStatus } from '../api/types'


/**
 * Status/quality pill.
 *
 * The class drives the colour, but the label is always rendered as text too.
 * Colour alone would exclude anyone who cannot distinguish these hues, which
 * for a quality rating is the whole meaning of the cell.
 */
export function Badge({
  kind,
  children,
}: {
  kind: BadgeKind
  children?: ReactNode
}) {
  // The class carries the colour; the label is always rendered as text so
  // the meaning never depends on hue alone.
  return <span className={`badge ${kind}`}>{children ?? titleCase(kind)}</span>
}

export function QualityBadge({ quality }: { quality: Quality }) {
  return <Badge kind={quality} />
}

export function StatusBadge({ status }: { status: RequestStatus }) {
  return <Badge kind={status}>{statusLabel(status)}</Badge>
}

export function PageHeading({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle: string
  action?: ReactNode
}) {
  return (
    <header className="pagehead row between">
      <div>
        <h1>{title}</h1>
        <p className="muted" style={{ margin: 0 }}>
          {subtitle}
        </p>
      </div>
      {action}
    </header>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <>
      <span className="spinner" />
      <span className="sr-only">{label}</span>
    </>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <Spinner label={label} /> <span style={{ marginLeft: 8 }}>{label}…</span>
    </div>
  )
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

/** Error surface with an optional retry, used wherever a fetch can fail. */
export function ErrorBox({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="errorbox" role="alert">
      <strong>{title}</strong>
      {message}
      {onRetry ? (
        <div className="retry">
          <button type="button" onClick={onRetry}>
            Try again
          </button>
        </div>
      ) : null}
    </div>
  )
}

export function TableWrap({ children }: { children: ReactNode }) {
  // Horizontal overflow is confined here, so a dense table never makes the
  // whole page scroll sideways on a narrow screen.
  return <div className="tablewrap">{children}</div>
}

export function Pagination({
  page,
  count,
  pageSize,
  onPage,
  busy = false,
}: {
  page: number
  count: number
  pageSize: number
  onPage: (page: number) => void
  busy?: boolean
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize))
  return (
    <div className="pagination">
      <small>
        {count} record{count === 1 ? '' : 's'} · Page {page} of {pages}
      </small>
      <div className="row">
        <button
          type="button"
          disabled={page <= 1 || busy}
          onClick={() => {
            onPage(page - 1)
          }}
        >
          Previous
        </button>
        <button
          type="button"
          disabled={page >= pages || busy}
          onClick={() => {
            onPage(page + 1)
          }}
        >
          Next
        </button>
      </div>
    </div>
  )
}

/**
 * Centred dialog.
 *
 * Handles the three things a dialog has to get right for keyboard users:
 * Escape closes, Tab cycles inside, and focus returns to whatever opened it.
 */
export function Modal({
  title,
  onClose,
  children,
  footer,
  wide = false,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const panel = useRef<HTMLElement>(null)
  const opener = useRef<Element | null>(null)

  useEffect(() => {
    opener.current = document.activeElement
    const first = panel.current?.querySelector<HTMLElement>(
      'input:not([type=hidden]),select,textarea,button',
    )
    first?.focus()
    return () => {
      // Returning focus matters: without it a keyboard user lands back at
      // the top of the document after every dialog.
      ;(opener.current as HTMLElement | null)?.focus?.()
    }
  }, [])

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLElement>) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = panel.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[href]',
      )
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (!first || !last) return
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    },
    [onClose],
  )

  return (
    <div
      className="modalback"
      onMouseDown={(event) => {
        // Only a click on the backdrop itself closes, not a drag that ends
        // there after starting inside the dialog.
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section
        className={`modal${wide ? ' widemodal' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={panel}
        onKeyDown={onKeyDown}
      >
        <header className="modalhead">
          <h2>{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close dialog">
            <Icon name="x" size={17} />
          </button>
        </header>
        {children}
        {footer ? <footer>{footer}</footer> : null}
      </section>
    </div>
  )
}

/** Transient confirmation, matching the prototype's toast. */
export function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 4500)
    return () => {
      window.clearTimeout(timer)
    }
  }, [message, onDismiss])

  return (
    <div className="toast" role="status">
      {message}
    </div>
  )
}

export function MetricCard({
  label,
  value,
  hint,
}: {
  label: string
  value: ReactNode
  hint?: string | undefined
}) {
  return (
    <div className="card">
      <small>{label}</small>
      <div className="metric">{value}</div>
      {hint ? <small>{hint}</small> : null}
    </div>
  )
}

export function BarRow({
  label,
  value,
  max,
}: {
  label: ReactNode
  value: number
  max: number
}) {
  const width = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="barrow">
      <div className="row between">
        <small>{label}</small>
        <strong>{value}</strong>
      </div>
      <div className="bar">
        <i style={{ width: `${String(width)}%` }} />
      </div>
    </div>
  )
}
