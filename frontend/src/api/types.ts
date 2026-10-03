export type Role = 'client' | 'operator' | 'admin'

export type RequestStatus =
  | 'submitted'
  | 'in_progress'
  | 'delivered'
  | 'accepted'
  | 'rejected'

export type Quality = 'good' | 'usable' | 'bad'

export type ExportStatus =
  | 'pending'
  | 'processing'
  | 'retry_wait'
  | 'completed'
  | 'failed'

/** Server-computed action names. The UI never derives these itself. */
export type AllowedAction =
  | 'start_work'
  | 'restart_work'
  | 'deliver'
  | 'accept'
  | 'reject'
  | 'assign'

export interface User {
  id: string
  name: string
  email: string
  role: Role
  organisation: string
  is_active: boolean
  created_at: string
}

export interface DatasetRequest {
  id: string
  client_id: string
  client_name: string
  task_name: string
  episodes_requested: number
  deadline: string
  notes: string
  status: RequestStatus
  assigned_count: number
  allowed_actions: AllowedAction[]
  created_at: string
  updated_at: string
  first_delivered_at: string | null
}

export interface Episode {
  id: string
  episode_id: string
  robot_id: string
  task_name: string
  recorded_at: string
  /** Decimal serialized as a string so no precision is lost in transit. */
  duration_seconds: string
  operator_name: string
  quality: Quality
  imported_at: string
  assigned_request_id: string | null
}

export interface ExportJob {
  status: ExportStatus
  attempts: number
  max_attempts: number
  last_error: string
  completed_at: string | null
}

export interface Assignment {
  id: string
  episode: Episode
  export_job: ExportJob | null
  assigned_by_name: string
  assigned_at: string
}

export interface AssignmentList {
  results: Assignment[]
  assigned_count: number
  episodes_requested: number
}

export interface StatusHistoryEntry {
  id: string
  previous_status: RequestStatus | null
  new_status: RequestStatus
  actor_id: string
  actor_name: string
  reason: string
  created_at: string
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface ImportIssue {
  line: number
  episode_id: string
  code: string
  reason: string
}

export interface ImportSummary {
  processed: number
  imported: number
  skipped: number
  duplicate: number
  conflict: number
  invalid: number
  skipped_blank: number
  issues: ImportIssue[]
  issues_truncated: boolean
}

export interface Analytics {
  start: string
  end: string
  totals: {
    episodes_recorded: number
    good_episodes: number
    requests_created: number
  }
  daily_episodes: { day: string; robot_id: string; count: number }[]
  request_counts: Record<RequestStatus, number>
  median_delivery_seconds: number | null
  top_good_tasks: { task_name: string; count: number }[]
  semantics: Record<string, string>
}

export interface AssignmentResult {
  created_ids: string[]
  existing_ids: string[]
  assigned_count: number
  episodes_requested: number
}
