/** Split navy-and-white login. Demo rows fill the form but never submit it. */

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
  const [showPassword, setShowPassword] = useState(false)
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
      <div className="login-card">
        <aside className="story">
          <div className="logo">
            <span className="mark">
              <Icon name="database" size={34} />
            </span>
            Dataset Desk
          </div>
          <div className="story-watermarks" aria-hidden="true">
            <span className="watermark watermark-layers"><Icon name="layers" size={112} /></span>
            <span className="watermark watermark-clipboard"><Icon name="clipboard-list" size={100} /></span>
            <span className="watermark watermark-box"><Icon name="box" size={112} /></span>
            <span className="watermark watermark-chart"><Icon name="chart-no-axes-combined" size={108} /></span>
          </div>
          <div className="story-copy">
            <p className="eyebrow">THE ROBOTICS DATA WORKSPACE</p>
            <h1>
              Your data.
              <br />
              One workspace.
            </h1>
            <p>
              Request, manage and deliver robotics
              <br />
              datasets, all in one place.
            </p>
          </div>
        </aside>

        <section className="login-right">
          <div className="login-form">
            <header className="login-heading">
              <h1>Welcome back</h1>
              <p className="lede">Sign in to your Dataset Desk workspace.</p>
            </header>

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
              <div className="pwfield">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  required
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value)
                  }}
                />
                <button
                  type="button"
                  className="pw-toggle"
                  aria-pressed={showPassword}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  onClick={() => {
                    setShowPassword((visible) => !visible)
                  }}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>

              <div className="submitrow">
                <button
                  className="primary wide"
                  type="submit"
                  disabled={busy}
                  aria-busy={busy}
                >
                  {busy ? <Spinner label="Signing in" /> : 'Sign in'}
                </button>
              </div>
              <div className="error" role="alert">{error}</div>
            </form>

            <div className="divider" aria-hidden="true">
              <span>Demo accounts</span>
            </div>

            <section className="demos" aria-label="Demo accounts">
              <p className="demo-helper">Select an account to fill the form, then sign in.</p>
              <ul className="demo-list">
                {DEMO_ACCOUNTS.map((account) => (
                  <li key={account.email}>
                    <button
                      type="button"
                      className={`demo demo-${account.role}`}
                      aria-pressed={
                        email === account.email && password === account.password
                      }
                      disabled={busy}
                      onClick={() => {
                        setEmail(account.email)
                        setPassword(account.password)
                        setError('')
                      }}
                    >
                      <span className="demo-avatar" aria-hidden="true">{account.name.charAt(0)}</span>
                      <span className="demo-account-copy">
                        <strong>{account.name}</strong>
                        <span className="demo-email">{account.email}</span>
                      </span>
                      <Badge kind={account.role} />
                    </button>
                  </li>
                ))}
              </ul>
            </section>

            <footer className="login-footer"><span>Dataset Request Desk</span></footer>
          </div>
        </section>
      </div>
    </section>
  )
}




