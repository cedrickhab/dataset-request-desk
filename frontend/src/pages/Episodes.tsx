/**
 * Episode inventory and CSV import. Staff only, enforced server-side.
 *
 * The import dialog does no business validation in the browser: it checks the
 * file size so an obviously oversized upload fails fast on a metered
 * connection, and everything else — headers, normalization, duplicates,
 * conflicts, per-row reasons — is decided by the one importer on the server
 * and reported back.
 */

import { useState } from 'react'

import { api } from '../api/client'
import { errorMessage, useAsync } from '../api/useAsync'
import type { ImportSummary, Quality } from '../api/types'
import { Icon } from '../components/Icon'
import {
  EmptyState,
  ErrorBox,
  Loading,
  Modal,
  PageHeading,
  Pagination,
  QualityBadge,
  Spinner,
  TableWrap,
  Toast,
} from '../components/ui'
import {
  formatDate,
} from '../components/format'

const PAGE_SIZE = 25
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

const QUALITIES: Quality[] = ['good', 'usable', 'bad']

export function Episodes() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [quality, setQuality] = useState('')
  const [availableOnly, setAvailableOnly] = useState(false)
  const [importing, setImporting] = useState(false)
  const [report, setReport] = useState<ImportSummary | null>(null)
  const [toast, setToast] = useState('')

  const state = useAsync(
    () =>
      api.listEpisodes({
        page,
        search,
        quality,
        ...(availableOnly ? { available: true } : {}),
      }),
    [page, search, quality, availableOnly],
  )

  return (
    <>
      <PageHeading
        title="Episodes"
        subtitle="Imported recording metadata and allocation inventory."
        action={
          <button
            type="button"
            className="primary"
            onClick={() => {
              setImporting(true)
            }}
          >
            <Icon name="upload" size={15} /> Import CSV
          </button>
        }
      />

      <section className="panel">
        <div className="tools">
          <label htmlFor="episode-search" className="sr-only">
            Search episodes
          </label>
          <input
            id="episode-search"
            placeholder="Search episode or robot"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setPage(1)
            }}
          />
          <label htmlFor="episode-quality" className="sr-only">
            Filter by quality
          </label>
          <select
            id="episode-quality"
            value={quality}
            onChange={(event) => {
              setQuality(event.target.value)
              setPage(1)
            }}
          >
            <option value="">All qualities</option>
            {QUALITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <label htmlFor="episode-availability" className="sr-only">
            Availability
          </label>
          <select
            id="episode-availability"
            value={availableOnly ? 'available' : 'all'}
            onChange={(event) => {
              setAvailableOnly(event.target.value === 'available')
              setPage(1)
            }}
          >
            <option value="all">All episodes</option>
            <option value="available">Assignable and unreserved</option>
          </select>
          {state.loading && state.data ? <Spinner label="Updating" /> : null}
        </div>

        {state.error ? (
          <ErrorBox message={state.error} onRetry={state.reload} />
        ) : state.loading && !state.data ? (
          <Loading label="Loading episodes" />
        ) : !state.data || state.data.results.length === 0 ? (
          <EmptyState>
            {search || quality || availableOnly
              ? 'No episodes match these filters.'
              : 'No episodes imported yet. Use Import CSV to load metadata.'}
          </EmptyState>
        ) : (
          <>
            <TableWrap>
              <table>
                <thead>
                  <tr>
                    <th>EPISODE / ROBOT</th>
                    <th>TASK</th>
                    <th>RECORDED</th>
                    <th>DURATION</th>
                    <th>QUALITY</th>
                    <th>ALLOCATION</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.results.map((episode) => (
                    <tr key={episode.id}>
                      <td>
                        <strong>{episode.episode_id}</strong>
                        <small>
                          {episode.robot_id} · {episode.operator_name}
                        </small>
                      </td>
                      <td>{episode.task_name}</td>
                      <td>{formatDate(episode.recorded_at)}</td>
                      <td>{episode.duration_seconds}s</td>
                      <td>
                        <QualityBadge quality={episode.quality} />
                      </td>
                      <td>
                        {episode.assigned_request_id ? (
                          <span className="badge delivered">Reserved</span>
                        ) : episode.quality === 'bad' ? (
                          <span className="muted">Not assignable</span>
                        ) : (
                          <span className="muted">Available</span>
                        )}
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
      </section>

      {report ? <ImportReport summary={report} /> : null}

      {importing ? (
        <ImportDialog
          onClose={() => {
            setImporting(false)
          }}
          onDone={(summary) => {
            setImporting(false)
            setReport(summary)
            setToast(
              `${String(summary.imported)} imported, ${String(summary.skipped)} skipped.`,
            )
            setPage(1)
            state.reload()
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

function ImportDialog({
  onClose,
  onDone,
}: {
  onClose: () => void
  onDone: (summary: ImportSummary) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    if (!file || busy) return
    if (file.size > MAX_UPLOAD_BYTES) {
      // Checked here purely to avoid spending a 10 MB upload on a metered
      // connection just to be told no. The server enforces the same limit.
      setError('That file is larger than 10 MB. Split it and import again.')
      return
    }
    setBusy(true)
    setError('')
    try {
      onDone(await api.importEpisodes(file))
    } catch (caught) {
      setError(errorMessage(caught, 'The import failed.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Import episode CSV"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="primary"
            disabled={!file || busy}
            aria-busy={busy}
            onClick={() => void submit()}
          >
            {busy ? <Spinner label="Importing" /> : 'Import file'}
          </button>
        </>
      }
    >
      <p className="muted">
        Bring recording metadata into the shared episode inventory. Importing the
        same file again is safe: existing episodes are skipped, never overwritten.
      </p>

      <label htmlFor="csv-file">Choose CSV file</label>
      <input
        id="csv-file"
        type="file"
        accept=".csv,text/csv"
        onChange={(event) => {
          setFile(event.target.files?.[0] ?? null)
          setError('')
        }}
      />
      {file ? (
        <p className="help">
          Selected: <strong>{file.name}</strong> ({Math.ceil(file.size / 1024)} KB)
        </p>
      ) : null}

      <p className="help">
        Required columns: episode_id, robot_id, task_name, recorded_at,
        duration_seconds, operator_name, quality.
      </p>
      <div className="alert">
        Metadata only — no video files are uploaded. Rows are validated on the
        server and reported line by line.
      </div>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
    </Modal>
  )
}

function ImportReport({ summary }: { summary: ImportSummary }) {
  return (
    <section className="panel" style={{ marginTop: 20 }}>
      <h2>Last import report</h2>
      <div className="reportcounts">
        <span>
          <strong>{summary.imported}</strong>
          <small>imported</small>
        </span>
        <span>
          <strong>{summary.skipped}</strong>
          <small>skipped</small>
        </span>
        <span>
          <strong>{summary.duplicate}</strong>
          <small>duplicates</small>
        </span>
        <span>
          <strong>{summary.conflict}</strong>
          <small>conflicts</small>
        </span>
        <span>
          <strong>{summary.invalid}</strong>
          <small>invalid</small>
        </span>
        <span>
          <strong>{summary.processed}</strong>
          <small>processed</small>
        </span>
      </div>

      {summary.issues.length === 0 ? (
        <p className="help">Every row was imported.</p>
      ) : (
        <>
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>LINE</th>
                  <th>EPISODE</th>
                  <th>OUTCOME</th>
                  <th>REASON</th>
                </tr>
              </thead>
              <tbody>
                {summary.issues.map((issue, index) => (
                  <tr key={`${String(issue.line)}-${String(index)}`}>
                    <td>{issue.line}</td>
                    <td>{issue.episode_id || <span className="muted">no id</span>}</td>
                    <td>
                      <span className={`badge ${issue.code === 'duplicate' ? '' : 'bad'}`}>
                        {issue.code}
                      </span>
                    </td>
                    <td>{issue.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          {summary.issues_truncated ? (
            <p className="help">
              Only the first {summary.issues.length} issues are listed. The counts
              above cover every row; use the import_episodes management command
              with --report for a complete JSONL report.
            </p>
          ) : null}
        </>
      )}
      {summary.skipped_blank > 0 ? (
        <p className="help">
          {summary.skipped_blank} blank row(s) were ignored and are not counted as
          processed.
        </p>
      ) : null}
    </section>
  )
}
