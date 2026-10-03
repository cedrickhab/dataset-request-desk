/**
 * Minimal data-fetching hook.
 *
 * No React Query: one hook covering load/error/refetch is all this app needs,
 * and a cache library is weight our users would pay for in mobile data
 * without getting much back. The trade-off is that we refetch explicitly
 * after a mutation instead of invalidating a cache.
 *
 * Two shape decisions worth knowing:
 *
 * `loading` is derived by comparing the key of the fetch we want against the
 * key of the one that last settled, rather than being set at the top of the
 * effect. Calling setState synchronously inside an effect triggers a second
 * render pass before the browser paints, which React's hooks lint flags.
 *
 * The previous `data` survives while a new key is in flight, so a page that
 * is refetching can keep its table on screen and just show a spinner,
 * instead of flashing an empty state.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from './client'

export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  /** Refetch. Stable, so it is safe in an effect's dependency list. */
  reload: () => void
}

interface Settled<T> {
  key: string
  data: T | null
  error: string | null
}

export function useAsync<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): AsyncState<T> {
  const [nonce, setNonce] = useState(0)
  const [settled, setSettled] = useState<Settled<T>>({
    // An empty key never matches a real one, so the first render is loading.
    key: '',
    data: null,
    error: null,
  })

  // Deps are primitives at every call site (ids, page numbers, filter
  // strings), so serializing them is a cheap, stable identity. Computed
  // inline rather than memoized: it is a pure function of values we already
  // have, and useMemo over a spread dependency list is not analyzable.
  const key = `${JSON.stringify(deps)}#${String(nonce)}`

  // Holds the newest fetcher without making it a dependency, so callers can
  // pass an inline closure without refetching on every render. Updated in an
  // effect declared before the fetching effect, so it is already current by
  // the time that one runs.
  const latest = useRef(fetcher)
  useEffect(() => {
    latest.current = fetcher
  }, [fetcher])

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    latest
      .current(controller.signal)
      .then((data) => {
        if (active) setSettled({ key, data, error: null })
      })
      .catch((caught: unknown) => {
        if (!active || controller.signal.aborted) return
        // A 401 is handled globally by the client, which drops the app to the
        // login form; rendering an error panel for it as well is noise.
        if (caught instanceof ApiError && caught.isUnauthenticated) {
          setSettled({ key, data: null, error: null })
          return
        }
        setSettled({
          key,
          data: null,
          error:
            caught instanceof ApiError
              ? caught.message
              : 'Could not load this. Check your connection and try again.',
        })
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [key])

  const reload = useCallback(() => {
    setNonce((value) => value + 1)
  }, [])

  return {
    data: settled.data,
    // Derived, not stored: true whenever the settled result is for an older key.
    loading: settled.key !== key,
    error: settled.key === key ? settled.error : null,
    reload,
  }
}

/** Turns a thrown value into a message suitable for display. */
export function errorMessage(caught: unknown, fallback = 'That did not work.'): string {
  return caught instanceof ApiError ? caught.message : fallback
}
