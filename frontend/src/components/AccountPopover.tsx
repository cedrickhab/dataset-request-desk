import { useEffect, useRef, useState } from 'react'

import { useAuth } from '../auth/useAuth'
import { Icon } from './Icon'

export function AccountPopover() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    panel.current?.focus()
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) {
        setOpen(false)
      }
    }
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setOpen(false)
        trigger.current?.focus()
      }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  if (!user) return null
  return (
    <div className="account" ref={root} onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
    }}>
      <button className="account-trigger" type="button" ref={trigger}
        aria-expanded={open} aria-controls="account-details"
        onClick={() => setOpen(!open)}>
        <span className="avatar" aria-hidden="true">{user.name.slice(0, 1)}</span>
        <span>{user.name}<small>{user.role}</small></span>
      </button>
      {open ? (
        <div className="account-panel" id="account-details" role="region"
          aria-label="Account details" tabIndex={-1} ref={panel}>
          <strong>{user.name}</strong>
          <dl>
            <dt>Email</dt><dd>{user.email}</dd>
            <dt>Role</dt><dd>{user.role}</dd>
            {user.organisation ? <><dt>Organisation</dt><dd>{user.organisation}</dd></> : null}
          </dl>
          <button type="button" onClick={() => void logout()}>
            <Icon name="log-out" size={15} /> Sign out
          </button>
        </div>
      ) : null}
    </div>
  )
}
