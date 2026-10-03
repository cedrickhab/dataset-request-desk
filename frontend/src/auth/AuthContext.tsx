/**
 * Session provider.
 *
 * The server is the only authority. This exists so the UI can show the right
 * navigation and avoid obviously-pointless calls; it is never a permission
 * check. A user whose role changed mid-session simply gets a 403 or 404 on
 * their next call, and the 401 handler below drops them to the login form.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, setUnauthenticatedHandler } from '../api/client'
import type { User } from '../api/types'
import { AuthContext, type AuthState } from './context'

/** Resolved session, or null once we know there isn't one. */
type Session = { status: 'loading' } | { status: 'ready'; user: User | null }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>({ status: 'loading' })

  const loadSession = useCallback(async (signal?: AbortSignal) => {
    try {
      const user = await api.me(signal)
      setSession({ status: 'ready', user })
    } catch {
      // A 401 here is the ordinary "not signed in yet" case, not an error
      // worth surfacing.
      setSession({ status: 'ready', user: null })
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    // Calls the API directly rather than going through loadSession, so that
    // every setSession here is plainly inside an async continuation. State
    // set synchronously during an effect costs an extra render pass before
    // the first paint.
    api
      .me(controller.signal)
      .then((user) => {
        setSession({ status: 'ready', user })
      })
      .catch(() => {
        // A 401 is the ordinary "not signed in yet" case, not an error.
        if (!controller.signal.aborted) setSession({ status: 'ready', user: null })
      })
    return () => {
      controller.abort()
    }
  }, [])

  useEffect(() => {
    // Any API call returning 401 clears the session, so an expired cookie
    // cannot leave a half-usable page on screen.
    setUnauthenticatedHandler(() => {
      setSession({ status: 'ready', user: null })
    })
    return () => {
      setUnauthenticatedHandler(null)
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const user = await api.login(email, password)
    setSession({ status: 'ready', user })
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      // Clear locally even if the call failed: the user asked to leave.
      setSession({ status: 'ready', user: null })
    }
  }, [])

  const refresh = useCallback(async () => {
    await loadSession()
  }, [loadSession])

  const value = useMemo<AuthState>(
    () => ({
      user: session.status === 'ready' ? session.user : null,
      loading: session.status === 'loading',
      login,
      logout,
      refresh,
    }),
    [session, login, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
