import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, rawApi, tryApi } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api', () => {
  it('returns the parsed JSON body on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { jobs: [1, 2] })))
    await expect(api('/api/jobs')).resolves.toEqual({ jobs: [1, 2] })
  })

  it('serializes an object body as JSON with the JSON content type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetchMock)
    await api('/api/tags', { method: 'POST', body: { name: 'cat' } })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/tags')
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(init.body).toBe('{"name":"cat"}')
  })

  it('sends no body or content type when body is omitted', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetchMock)
    await api('/api/jobs', { method: 'POST' })
    const [, init] = fetchMock.mock.calls[0]
    expect(init.body).toBeUndefined()
    expect(init.headers).toBeUndefined()
  })

  it('throws ApiError with the backend detail.error.message on failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(409, { detail: { error: { code: 'collision', message: 'Already there' } } })),
    )
    const error: unknown = await api('/api/files/x/move').catch((err) => err)
    if (!(error instanceof ApiError)) throw new Error('expected ApiError')
    expect(error.status).toBe(409)
    expect(error.message).toBe('Already there')
    expect(error.code).toBe('collision')
  })

  it('falls back to "HTTP <status>" when the error body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 502 })))
    const error: unknown = await api('/api/health').catch((err) => err)
    if (!(error instanceof ApiError)) throw new Error('expected ApiError')
    expect(error.message).toBe('HTTP 502')
    expect(error.code).toBeUndefined()
  })

  it('resolves undefined for a success response without a JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 200 })))
    await expect(api('/api/jobs/x')).resolves.toBeUndefined()
  })

  it('propagates network failures as-is', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api('/api/jobs')).rejects.toThrow('Failed to fetch')
  })
})

describe('tryApi', () => {
  it('returns null on HTTP errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(500, { detail: null })))
    await expect(tryApi('/api/jobs')).resolves.toBeNull()
  })

  it('returns null on network failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(tryApi('/api/jobs')).resolves.toBeNull()
  })

  it('returns the body on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { ok: true })))
    await expect(tryApi('/api/health')).resolves.toEqual({ ok: true })
  })
})

describe('rawApi', () => {
  it('returns the Response without status checks', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('blob-bytes', { status: 404 })))
    const res = await rawApi('/api/settings/provider-entries/export')
    expect(res.status).toBe(404)
    await expect(res.text()).resolves.toBe('blob-bytes')
  })

  it('aborts through fetchWithTimeout when timeoutMs is set', async () => {
    const fetchMock = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await expect(rawApi('/api/tag-lab/run', { method: 'POST', body: {}, timeoutMs: 1 })).rejects.toThrow('aborted')
  })
})
