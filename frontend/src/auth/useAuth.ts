/**
 * Session hooks.
 *
 * Separate module so AuthContext.tsx exports only the provider component and
 * fast refresh keeps working.
 *
 * These role predicates decide what the navigation shows. They are never a
 * permission check: the server re-evaluates the role on every request.
 */

import { useContext } from 'react'

import { AuthContext, type AuthState } from './context'

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}

export function useRoles() {
  const { user } = useAuth()
  return {
    isStaff: user?.role === 'operator' || user?.role === 'admin',
    isAdmin: user?.role === 'admin',
    isClient: user?.role === 'client',
  }
}
