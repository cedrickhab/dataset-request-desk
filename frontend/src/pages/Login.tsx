/**
 * Split login, matching the prototype: amber product panel on the left,
 * credentials on the right, demo accounts below the fields.
 *
 * The demo buttons fill the form; they never log in by themselves. These are
 * the seeded reviewer accounts from seed/users.json and are the only
 * credentials shown anywhere in the UI. The personal administrator account is
 * configured from the environment and deliberately absent here.
 */

import { useState, type FormEvent } from 'react'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { Badge, Spinner } from '../components/ui'
import type { Role } from '../api/types'

interface DemoAccount {
  name: string
  email: string
  password: string
  role: Role
}

const DEMO_ACCOUNTS: DemoAccount[] = [
  { name: 'Ada Admin', email: 'admin@example.com', password: 'admin123', role: 'admin' },
  { name: 'Olu Operator', email: 'ops1@example.com', password: 'ops123', role: 'operator' },
  { name: 'Odile Operator', email: 'ops2@example.com', password: 'ops123', role: 'operator' },
  {
    name: 'Acme Robotics',
    email: 'client-a@example.com',
    password: 'client123',
    role: 'client',
  },
  { name: 'Beta Labs', email: 'client-b@example.com', password: 'client123', role: 'client' },
]

export function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await login(email.trim(), password)
    } catch (caught) {
      // The server returns one generic message for bad password, unknown
      // email and deactivated account. Showing it verbatim keeps the UI from
      // becoming an account-enumeration oracle the API refuses to be.
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not sign in. Check your connection and try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="login">
      <aside className="story">
        <div className="logo">
          <span className="mark">
            <Icon name="database" size={19} />
          </span>
          Dataset Desk
        </div>
        <div>
          <small style={{ color: '#68491c' }}>THE ROBOTICS DATA WORKSPACE</small>
          <h1>
            Your data.
            <br />
            One workspace.
          </h1>
          <p>Manage episodes and client requests.</p>
        </div>
        <footer>
          <small>Dataset Request Desk</small>
        </footer>
      </aside>

      <section className="login-right">
        <div className="login-form">
          <h1>Welcome back</h1>
          <p className="muted">Sign in to Dataset Desk.</p>

          <form onSubmit={onSubmit} noValidate>
            <label htmlFor="email">Email address</label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              placeholder="you@company.com"
              required
              value={email}
              onChange={(event) => {
                setEmail(event.target.value)
              }}
            />

            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              placeholder="Enter your password"
              required
              value={password}
              onChange={(event) => {
                setPassword(event.target.value)
              }}
            />

            <button
              className="primary wide"
              style={{ marginTop: 12 }}
              type="submit"
              disabled={busy}
              aria-busy={busy}
            >
              {busy ? <Spinner label="Signing in" /> : 'Sign in'}
            </button>

            {/* role="alert" so the failure is announced, not just shown. */}
            <div className="error" role="alert">
              {error}
            </div>
          </form>

          <section className="demos">
            <h3>Try a demo account</h3>
            <small>Click an account to fill the credentials, then sign in.</small>
            {DEMO_ACCOUNTS.map((account) => (
              <button
                type="button"
                className="demo"
                key={account.email}
                onClick={() => {
                  setEmail(account.email)
                  setPassword(account.password)
                  setError('')
                }}
              >
                <span>
                  <strong>{account.name}</strong>
                  <br />
                  <small>
                    {account.email} · {account.password}
                  </small>
                </span>
                <Badge kind={account.role} />
              </button>
            ))}
          </section>
        </div>
      </section>
    </section>
  )
}
