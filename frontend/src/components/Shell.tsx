/**
 * Sidebar + topbar shell, matching the prototype's 208px grid.
 *
 * The navigation is filtered by role for usability only. Hiding a link is not
 * a permission: the server refuses the underlying call regardless, and the
 * backend tests assert that directly.
 */

import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { useAuth, useRoles } from '../auth/useAuth'
import { Icon, type IconName } from './Icon'
import { Spinner } from './ui'
import { AccountPopover } from './AccountPopover'

interface NavItem {
  to: string
  label: string
  icon: IconName
}

const STAFF_NAV: NavItem[] = [
  { to: '/', label: 'Overview', icon: 'layout-dashboard' },
  { to: '/requests', label: 'Requests', icon: 'clipboard-list' },
  { to: '/episodes', label: 'Episodes', icon: 'database' },
  { to: '/analytics', label: 'Analytics', icon: 'chart-no-axes-combined' },
]

const ADMIN_NAV: NavItem = { to: '/users', label: 'Users', icon: 'users' }

const CLIENT_NAV: NavItem[] = [
  { to: '/', label: 'Overview', icon: 'layout-dashboard' },
  { to: '/requests', label: 'My requests', icon: 'clipboard-list' },
]

export function Shell() {
  const { user } = useAuth()
  const { isStaff, isAdmin } = useRoles()
  const location = useLocation()

  if (!user) return null

  const items = isStaff ? [...STAFF_NAV, ...(isAdmin ? [ADMIN_NAV] : [])] : CLIENT_NAV

  const current =
    items.find((item) => item.to !== '/' && location.pathname.startsWith(item.to))?.label ??
    (location.pathname.startsWith('/requests/') ? 'Request details' : 'Overview')

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <aside className="sidebar">
        <div className="logo">
          <span className="mark">
            <Icon name="database" size={19} />
          </span>
          Dataset Desk
        </div>
        <small style={{ padding: '0 13px', marginBottom: 10, display: 'block' }}>
          WORKSPACE
        </small>

        <nav aria-label="Main">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `nav${isActive ? ' active' : ''}`}
            >
              <span>
                <Icon name={item.icon} />
              </span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <small>Signed in as</small>
          <p style={{ fontSize: 12, margin: '6px 0' }}>{user.email}</p>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          {/* Single text node: several tests and screen readers match it whole. */}
          <span className="breadcrumb">Workspace / {current}</span>
          <AccountPopover />
        </header>

        <main className="main" id="main">
          <Outlet />
        </main>
        <footer className="workspace-footer">
          <span>Dataset Request Desk</span>
          {/* Real project metadata only: injected from package.json by Vite. */}
          <span>v{__APP_VERSION__}</span>
        </footer>
      </div>
    </div>
  )
}

export function FullPageLoading() {
  return (
    <div className="loading" style={{ paddingTop: '22vh' }} role="status">
      <Spinner label="Loading Dataset Desk" />
      <p className="muted">Loading Dataset Desk…</p>
    </div>
  )
}
