/**
 * API client.
 *
 * Session cookies only. No token is ever read from or written to
 * localStorage: the session cookie is HttpOnly, so script on this page
 * cannot read it even if an XSS slipped through, and there is no bearer
 * token sitting in storage for one to steal.
 *
 * The CSRF token is a different matter. It is deliberately readable so it
 * can be echoed in the X-CSRFToken header; it is not a credential on its own.
 */

import type {
  Analytics,
  Assignment,
  AssignmentList,
  AssignmentResult,
  DatasetRequest,
  Episode,
  ImportSummary,
  Paginated,
  Role,
  StatusHistoryEntry,
  User,
} from './types'

export interface ApiErrorBody {
  error: { code: string; message: string; fields?: Record<string, string[]> }
  request_id: string | null
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, string[]>
  readonly requestId: string | null

  constructor(status: number, body: ApiErrorBody | null, fallback: string) {
    super(body?.error.message ?? fallback)
    this.name = 'ApiError'
    this.status = status
    this.code = body?.error.code ?? 'error'
    this.fields = body?.error.fields ?? {}
    this.requestId = body?.request_id ?? null
  }

  /** The stored state moved under us; the caller should refetch. */
  get isConflict(): boolean {
    return this.status === 409
  }

  get isUnauthenticated(): boolean {
    return this.status === 401
  }

  /** First message for a field, for inline form errors. */
  fieldError(name: string): string | undefined {
    return this.fields[name]?.[0]
  }
}

function readCookie(name: string): string | null {
  const prefix = `${name}=`
  for (const part of document.cookie.split('; ')) {
    if (part.startsWith(prefix)) return decodeURIComponent(part.slice(prefix.length))
  }
  return null
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

/** Called when the server reports the session is gone, so the app can reset. */
let onUnauthenticated: (() => void) | null = null
export function setUnauthenticatedHandler(handler: (() => void) | null): void {
  onUnauthenticated = handler
}

export async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie('csrftoken')
  if (existing) return existing
  // The one anonymous endpoint: it sets the cookie and returns the token.
  const response = await fetch('/api/auth/csrf', { credentials: 'same-origin' })
  if (!response.ok) throw new ApiError(response.status, null, 'Could not start a session.')
  const body = (await response.json()) as { csrf_token: string }
  return body.csrf_token
}

interface RequestOptions {
  method?: string
  body?: unknown
  /** Set for multipart; the browser must choose the boundary itself. */
  formData?: FormData
  signal?: AbortSignal
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }

  if (UNSAFE.has(method)) {
    headers['X-CSRFToken'] = await ensureCsrfToken()
  }

  let body: BodyInit | undefined
  if (options.formData) {
    // No Content-Type header: fetch sets it with the multipart boundary.
    body = options.formData
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  const init: RequestInit = {
    method,
    headers,
    // Send the session cookie. 'same-origin' rather than 'include' because
    // the API is served from this same origin by the proxy.
    credentials: 'same-origin',
  }
  if (body !== undefined) init.body = body
  if (options.signal) init.signal = options.signal

  const response = await fetch(path, init)

  if (response.status === 204) return undefined as T

  const text = await response.text()
  let parsed: unknown = null
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = null
    }
  }

  if (!response.ok) {
    const error = new ApiError(
      response.status,
      parsed as ApiErrorBody | null,
      `Request failed (${String(response.status)}).`,
    )
    // An expired or revoked session surfaces here on any call; tell the app
    // once rather than making every caller handle it.
    if (error.isUnauthenticated) onUnauthenticated?.()
    throw error
  }

  return parsed as T
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const rendered = search.toString()
  return rendered ? `?${rendered}` : ''
}

export const api = {
  // --- auth ---
  async login(email: string, password: string): Promise<User> {
    return request<User>('/api/auth/login', {
      method: 'POST',
      body: { email, password },
    })
  },

  async logout(): Promise<void> {
    await request<void>('/api/auth/logout', { method: 'POST' })
  },

  async me(signal?: AbortSignal): Promise<User> {
    return request<User>('/api/auth/me', signal ? { signal } : {})
  },

  // --- requests ---
  async listRequests(
    params: { status?: string; search?: string; page?: number } = {},
  ): Promise<Paginated<DatasetRequest>> {
    return request<Paginated<DatasetRequest>>(`/api/requests${query(params)}`)
  },

  async createRequest(input: {
    task_name: string
    episodes_requested: number
    deadline: string
    notes: string
  }): Promise<DatasetRequest> {
    return request<DatasetRequest>('/api/requests', { method: 'POST', body: input })
  },

  async getRequest(id: string, signal?: AbortSignal): Promise<DatasetRequest> {
    return request<DatasetRequest>(`/api/requests/${id}`, signal ? { signal } : {})
  },

  async getHistory(id: string): Promise<StatusHistoryEntry[]> {
    return request<StatusHistoryEntry[]>(`/api/requests/${id}/history`)
  },

  async transition(id: string, status: string, reason?: string): Promise<DatasetRequest> {
    return request<DatasetRequest>(`/api/requests/${id}/transitions`, {
      method: 'POST',
      body: reason ? { status, reason } : { status },
    })
  },

  // --- assignments ---
  async listAssignments(id: string, signal?: AbortSignal): Promise<AssignmentList> {
    return request<AssignmentList>(
      `/api/requests/${id}/assignments`,
      signal ? { signal } : {},
    )
  },

  async assign(id: string, episodeIds: string[]): Promise<AssignmentResult> {
    return request<AssignmentResult>(`/api/requests/${id}/assignments`, {
      method: 'POST',
      body: { episode_ids: episodeIds },
    })
  },

  async removeAssignment(requestId: string, assignmentId: string): Promise<void> {
    await request<void>(`/api/requests/${requestId}/assignments/${assignmentId}`, {
      method: 'DELETE',
    })
  },

  // --- episodes ---
  async listEpisodes(
    params: {
      task_name?: string
      quality?: string
      available?: boolean
      search?: string
      page?: number
      page_size?: number
    } = {},
  ): Promise<Paginated<Episode>> {
    return request<Paginated<Episode>>(`/api/episodes${query(params)}`)
  },

  async importEpisodes(file: File): Promise<ImportSummary> {
    const formData = new FormData()
    formData.append('file', file)
    return request<ImportSummary>('/api/episodes/import', {
      method: 'POST',
      formData,
    })
  },

  // --- analytics ---
  async analytics(start: string, end: string): Promise<Analytics> {
    return request<Analytics>(`/api/analytics${query({ start, end })}`)
  },

  // --- users ---
  async listUsers(params: { search?: string; page?: number } = {}): Promise<Paginated<User>> {
    return request<Paginated<User>>(`/api/users${query(params)}`)
  },

  async createUser(input: {
    name: string
    email: string
    password: string
    role: Role
    organisation?: string
  }): Promise<User> {
    return request<User>('/api/users', { method: 'POST', body: input })
  },

  async updateUser(
    id: string,
    changes: { role?: Role; is_active?: boolean },
  ): Promise<User> {
    return request<User>(`/api/users/${id}`, { method: 'PATCH', body: changes })
  },
}

export type { Assignment }
