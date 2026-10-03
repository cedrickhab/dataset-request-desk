/** The context object and its type, kept apart from the provider component. */

import { createContext } from 'react'

import type { User } from '../api/types'

export interface AuthState {
  user: User | null
  /** True until the initial /auth/me has resolved one way or the other. */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** Re-read the session, e.g. after an admin changes their own role. */
  refresh: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)
