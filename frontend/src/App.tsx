/**
 * Routing.
 *
 * Route guards here are for usability: they keep a client from landing on an
 * empty staff screen and send a signed-out user to the login form. They are
 * not security. Every endpoint behind these screens re-checks the role, and
 * the backend tests assert that directly rather than through the UI.
 *
 * Episodes, Analytics and Users are lazily loaded. Most sign-ins are clients,
 * who can never open any of them, so shipping those three screens in the
 * initial bundle would make every client pay for staff tooling in mobile
 * data. The guards below only render the lazy element after the role check,
 * so the chunk is never even requested for a client.
 */

import { Suspense, lazy, type ReactElement } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth, useRoles } from './auth/useAuth'
import { FullPageLoading, Shell } from './components/Shell'
import { Loading } from './components/ui'
import { Dashboard } from './pages/Dashboard'
import { Login } from './pages/Login'
import { RequestDetail } from './pages/RequestDetail'
import { Requests } from './pages/Requests'

const Episodes = lazy(() =>
  import('./pages/Episodes').then((module) => ({ default: module.Episodes })),
)
const Analytics = lazy(() =>
  import('./pages/Analytics').then((module) => ({ default: module.Analytics })),
)
const Users = lazy(() =>
  import('./pages/Users').then((module) => ({ default: module.Users })),
)

function StaffOnly({ children }: { children: ReactElement }) {
  const { isStaff } = useRoles()
  if (!isStaff) return <Navigate to="/" replace />
  return <Suspense fallback={<Loading label="Loading" />}>{children}</Suspense>
}

function AdminOnly({ children }: { children: ReactElement }) {
  const { isAdmin } = useRoles()
  if (!isAdmin) return <Navigate to="/" replace />
  return <Suspense fallback={<Loading label="Loading" />}>{children}</Suspense>
}

export function App() {
  const { user, loading } = useAuth()

  // Wait for the initial /auth/me before deciding. Rendering the login form
  // first would flash it in front of an already-signed-in user on reload.
  if (loading) return <FullPageLoading />

  if (!user) return <Login />

  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Dashboard />} />
        <Route path="requests" element={<Requests />} />
        <Route path="requests/:id" element={<RequestDetail />} />
        <Route
          path="episodes"
          element={
            <StaffOnly>
              <Episodes />
            </StaffOnly>
          }
        />
        <Route
          path="analytics"
          element={
            <StaffOnly>
              <Analytics />
            </StaffOnly>
          }
        />
        <Route
          path="users"
          element={
            <AdminOnly>
              <Users />
            </AdminOnly>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
