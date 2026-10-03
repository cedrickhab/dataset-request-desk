/**
 * Labels and formatters.
 *
 * Separate from ui.tsx so that file exports only components: mixing
 * components and plain helpers in one module breaks Vite's fast refresh for
 * the whole file.
 */

import type { ExportStatus, Quality, RequestStatus, Role } from '../api/types'

/** Everything the Badge component accepts. Kept as a closed union so a typo
 *  is a type error rather than a silently unstyled pill. */
export type BadgeKind = RequestStatus | Quality | ExportStatus | Role

const STATUS_LABELS: Record<RequestStatus, string> = {
  submitted: 'Submitted',
  in_progress: 'In progress',
  delivered: 'Delivered',
  accepted: 'Accepted',
  rejected: 'Rejected',
}

const EXPORT_LABELS: Record<ExportStatus, string> = {
  pending: 'Pending',
  processing: 'Processing',
  retry_wait: 'Waiting to retry',
  completed: 'Completed',
  failed: 'Failed',
}

export function statusLabel(status: RequestStatus): string {
  return STATUS_LABELS[status]
}

export function exportLabel(status: ExportStatus): string {
  return EXPORT_LABELS[status]
}

/** Timestamps arrive as UTC ISO strings and are shown in the viewer's zone. */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', { dateStyle: 'medium' })
}

/** Null renders as an em dash: "no deliveries yet" is not "zero hours". */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const hours = seconds / 3600
  if (hours >= 1) return `${hours.toFixed(1)}h`
  return `${String(Math.round(seconds / 60))}m`
}

/** Local calendar date as YYYY-MM-DD, for date input min attributes. */
export function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${String(date.getFullYear())}-${month}-${day}`
}
