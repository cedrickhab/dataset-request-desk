/**
 * User administration. Admin only, enforced server-side.
 *
 * The two protective rules (no demoting the last active admin, no
 * deactivating yourself) are enforced in a locked transaction on the server.
 * This page surfaces the resulting 409 message rather than trying to predict
 * the rules, which would risk the UI and the server disagreeing.
 */

import { useState, type FormEvent } from 'react'

import { api, ApiError } from '../api/client'
import { errorMessage, useAsync } from '../api/useAsync'
import type { Role, User } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import {
  Badge,
  EmptyState,
  ErrorBox,
  Loading,
  Modal,
  PageHeading,
  Pagination,
  Spinner,
  TableWrap,
  Toast,
} from '../components/ui'

const PAGE_SIZE = 25
const ROLES: Role[] = ['client', 'operator', 'admin']

export function Users() {
  const { user: currentUser, refresh } = useAuth()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  const [actionError, setActionError] = useState('')
  const [toast, setToast] = useState('')

  const state = useAsync(() => api.listUsers({ page, search }), [page, search])

  async function toggleActive(target: User) {
    setPending(target.id)
    setActionError('')
    try {
      await api.updateUser(target.id, { is_active: !target.is_active })
      setToast(`${target.name} ${target.is_active ? 'deactivated' : 'reactivated'}.`)
      state.reload()
    } catch (caught) {
      setActionError(errorMessage(caught, 'Could not update that account.'))
    } finally {
      setPending(null)
    }
  }

  return (
    <>
      <PageHeading
        title="Users"
        subtitle="Manage account access and roles."
        action={
          <button
            type="button"
            className="primary"
            onClick={() => {
              setCreating(true)
            }}
          >
            <Icon name="plus" size={15} /> Create user
          </button>
        }
      />

      {actionError ? <ErrorBox message={actionError} /> : null}

      <section className="panel">
        <div className="tools">
          <label htmlFor="user-search" className="sr-only">
            Search users
          </label>
          <input
            id="user-search"
            placeholder="Search name or email"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setPage(1)
            }}
          />
          {state.loading && state.data ? <Spinner label="Updating" /> : null}
        </div>

        {state.error ? (
          <ErrorBox message={state.error} onRetry={state.reload} />
        ) : state.loading && !state.data ? (
          <Loading label="Loading users" />
        ) : !state.data || state.data.results.length === 0 ? (
          <EmptyState>No users match this search.</EmptyState>
        ) : (
          <>
            <TableWrap>
              <table>
                <thead>
                  <tr>
                    <th>NAME / EMAIL</th>
                    <th>ROLE</th>
                    <th>STATUS</th>
                    <th>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.results.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.name}</strong>
                        <small>
                          {row.email}
                          {row.id === currentUser?.id ? ' · you' : ''}
                        </small>
                      </td>
                      <td>
                        <Badge kind={row.role} />
                      </td>
                      <td>
                        <Badge kind={row.is_active ? 'accepted' : 'rejected'}>
                          {row.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td>
                        <button
                          type="button"
                          disabled={pending !== null}
                          onClick={() => {
                            setEditing(row)
                          }}
                        >
                          Edit role
                        </button>{' '}
                        <button
                          type="button"
                          className={row.is_active ? 'danger' : ''}
                          disabled={pending !== null}
                          aria-busy={pending === row.id}
                          onClick={() => void toggleActive(row)}
                        >
                          {row.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <Pagination
              page={page}
              count={state.data.count}
              pageSize={PAGE_SIZE}
              onPage={setPage}
              busy={state.loading}
            />
          </>
        )}

        <p className="help">
          The last active administrator cannot be demoted or deactivated, and you
          cannot deactivate your own account. Accounts are never deleted, so
          request and assignment history stays attributable.
        </p>
      </section>

      {creating ? (
        <CreateUserDialog
          onClose={() => {
            setCreating(false)
          }}
          onCreated={(created) => {
            setCreating(false)
            setToast(`${created.name} created.`)
            state.reload()
          }}
        />
      ) : null}

      {editing ? (
        <EditRoleDialog
          user={editing}
          onClose={() => {
            setEditing(null)
          }}
          onSaved={async (updated) => {
            setEditing(null)
            setToast(`${updated.name} is now ${updated.role}.`)
            state.reload()
            // If an admin changed their own role, the navigation has to
            // follow immediately rather than after the next reload.
            if (updated.id === currentUser?.id) await refresh()
          }}
        />
      ) : null}

      {toast ? (
        <Toast
          message={toast}
          onDismiss={() => {
            setToast('')
          }}
        />
      ) : null}
    </>
  )
}

function CreateUserDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (created: User) => void
}) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('client')
  const [organisation, setOrganisation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setFields({})
    try {
      onCreated(
        await api.createUser({ name, email, password, role, organisation }),
      )
    } catch (caught) {
      if (caught instanceof ApiError && Object.keys(caught.fields).length > 0) {
        const mapped: Record<string, string> = {}
        for (const [key, messages] of Object.entries(caught.fields)) {
          if (messages[0]) mapped[key] = messages[0]
        }
        setFields(mapped)
        setError('Check the highlighted fields.')
      } else {
        setError(errorMessage(caught, 'Could not create that account.'))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Create user"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="submit"
            form="create-user"
            className="primary"
            disabled={busy}
            aria-busy={busy}
          >
            {busy ? <Spinner label="Creating" /> : 'Create user'}
          </button>
        </>
      }
    >
      <form id="create-user" onSubmit={onSubmit} noValidate>
        <label htmlFor="user-name">Full name</label>
        <input
          id="user-name"
          required
          maxLength={150}
          autoComplete="off"
          value={name}
          aria-invalid={fields.name ? true : undefined}
          onChange={(event) => {
            setName(event.target.value)
          }}
        />
        {fields.name ? <p className="fielderror">{fields.name}</p> : null}

        <label htmlFor="user-email">Email address</label>
        <input
          id="user-email"
          type="email"
          required
          autoComplete="off"
          value={email}
          aria-invalid={fields.email ? true : undefined}
          onChange={(event) => {
            setEmail(event.target.value)
          }}
        />
        {fields.email ? <p className="fielderror">{fields.email}</p> : null}

        <div className="formgrid">
          <div>
            <label htmlFor="user-role">Role</label>
            <select
              id="user-role"
              value={role}
              onChange={(event) => {
                setRole(event.target.value as Role)
              }}
            >
              {ROLES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="user-org">Organisation (optional)</label>
            <input
              id="user-org"
              maxLength={150}
              value={organisation}
              onChange={(event) => {
                setOrganisation(event.target.value)
              }}
            />
          </div>
        </div>

        <label htmlFor="user-password">Temporary password</label>
        <input
          id="user-password"
          type="password"
          required
          // new-password so a browser does not autofill the admin's own
          // credentials into an account-creation form.
          autoComplete="new-password"
          value={password}
          aria-invalid={fields.password ? true : undefined}
          onChange={(event) => {
            setPassword(event.target.value)
          }}
        />
        {fields.password ? <p className="fielderror">{fields.password}</p> : null}

        <p className="help">
          Checked against Django&apos;s password validators and stored only as a
          hash. Share it over a channel the recipient already trusts.
        </p>

        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  )
}

function EditRoleDialog({
  user,
  onClose,
  onSaved,
}: {
  user: User
  onClose: () => void
  onSaved: (updated: User) => void | Promise<void>
}) {
  const [role, setRole] = useState<Role>(user.role)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function save() {
    if (busy || role === user.role) {
      onClose()
      return
    }
    setBusy(true)
    setError('')
    try {
      await onSaved(await api.updateUser(user.id, { role }))
    } catch (caught) {
      setError(errorMessage(caught, 'Could not change that role.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={`Change role for ${user.name}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="primary"
            disabled={busy}
            aria-busy={busy}
            onClick={() => void save()}
          >
            {busy ? <Spinner label="Saving" /> : 'Save role'}
          </button>
        </>
      }
    >
      <label htmlFor="edit-role">Role</label>
      <select
        id="edit-role"
        value={role}
        onChange={(event) => {
          setRole(event.target.value as Role)
        }}
      >
        {ROLES.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </select>
      <p className="help">
        Roles are mutually exclusive. A change takes effect on this user&apos;s
        very next request, including any session they already have open.
      </p>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
    </Modal>
  )
}
