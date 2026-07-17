// Central HTTP client for the backend API. Every component/context calls the
// backend through these helpers instead of inline `fetch('/api/...')`, so the
// endpoint list stays greppable in one place per call site and error handling
// is uniform: a failed call throws `ApiError` carrying the backend's
// structured `detail` payload (FastAPI convention `{detail: {error: {code,
// message}}}`), with `message` already resolved the way call sites used to
// compute it by hand (`json?.detail?.error?.message ?? "HTTP <status>"`).
import { fetchWithTimeout } from '../utils/fetchWithTimeout'

export class ApiError extends Error {
  readonly status: number
  /** Parsed `detail` field of the error response body, if the body was JSON. */
  readonly detail: unknown

  constructor(status: number, detail: unknown) {
    const errorObj = (detail as { error?: { message?: string } } | null)?.error
    super(errorObj?.message ?? `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }

  /** Backend error code (`detail.error.code`), if present. */
  get code(): string | undefined {
    return (this.detail as { error?: { code?: string } } | null)?.error?.code
  }
}

export interface ApiInit {
  method?: string
  /** JSON-serialized into the request body with `Content-Type: application/json`. */
  body?: unknown
  /** Client-side ceiling on the whole request (aborts via AbortController). */
  timeoutMs?: number
  signal?: AbortSignal
}

function toRequestInit(init: ApiInit): RequestInit {
  const { method, body, signal } = init
  const requestInit: RequestInit = { method, signal }
  if (body !== undefined) {
    requestInit.headers = { 'Content-Type': 'application/json' }
    requestInit.body = JSON.stringify(body)
  }
  return requestInit
}

/** Raw variant: performs the request (with JSON body/timeout handling) and
 * returns the `Response` as-is, without status checks or body parsing. For
 * non-JSON payloads (blob downloads) and callers that inspect the response
 * themselves. */
export async function rawApi(path: string, init: ApiInit = {}): Promise<Response> {
  const requestInit = toRequestInit(init)
  if (init.timeoutMs !== undefined) {
    return fetchWithTimeout(path, requestInit, init.timeoutMs)
  }
  return fetch(path, requestInit)
}

/** JSON call: resolves with the parsed response body on 2xx, throws `ApiError`
 * on any non-2xx status. Network failures reject with the underlying error. */
export async function api<T = unknown>(path: string, init: ApiInit = {}): Promise<T> {
  const res = await rawApi(path, init)
  if (!res.ok) {
    const json = await res.json().catch(() => null)
    throw new ApiError(res.status, json?.detail ?? null)
  }
  return (await res.json().catch(() => undefined)) as T
}

/** Best-effort variant: resolves `null` instead of throwing, on any failure
 * (HTTP error or network error). For polling and background refreshes where
 * the caller keeps the last known state. */
export async function tryApi<T = unknown>(path: string, init: ApiInit = {}): Promise<T | null> {
  try {
    return await api<T>(path, init)
  } catch {
    return null
  }
}
