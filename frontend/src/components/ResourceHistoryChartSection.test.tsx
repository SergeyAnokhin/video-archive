// @vitest-environment jsdom
//
// Component test for the Settings -> Performance CPU/memory/network history
// chart (chat request 2026-07-25): fetches settings once (for poll cadence),
// fetches history for the selected range, and refetches when the range
// selector changes. The backend endpoint's own downsampling/normalization
// logic is covered in backend/tests/test_resource_monitor_history.py.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../i18n'
import { ResourceHistoryChartSection } from './ResourceHistoryChartSection'

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

function fetchRouter(handlers: Record<string, () => Response>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = init?.method ?? 'GET'
    const handler = handlers[`${method} ${url}`]
    if (!handler) {
      throw new Error(`Unhandled fetch in test: ${method} ${url}`)
    }
    return handler()
  })
}

const SETTINGS = { enabled: true, interval_seconds: 30, updated_at: '2026-01-01T00:00:00Z' }

const HISTORY_4H = {
  range_seconds: 14400,
  network_scale_bytes_per_sec: 100000,
  points: [
    { timestamp: 1000, cpu_percent: 10, memory_percent: 20, network_percent: 30 },
    { timestamp: 2000, cpu_percent: 15, memory_percent: 25, network_percent: 40 },
  ],
}

const HISTORY_30M = {
  range_seconds: 1800,
  network_scale_bytes_per_sec: 100000,
  points: [{ timestamp: 3000, cpu_percent: 50, memory_percent: 60, network_percent: 70 }],
}

describe('ResourceHistoryChartSection', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('loads the default 4h range and renders the latest values in the legend', async () => {
    vi.stubGlobal(
      'fetch',
      fetchRouter({
        'GET /api/resource-monitor-settings': () => jsonResponse(SETTINGS),
        'GET /api/resource-monitor-history?range=4h': () => jsonResponse(HISTORY_4H),
      }),
    )

    render(<ResourceHistoryChartSection />)

    await waitFor(() => screen.getByText('15%'))
    expect(screen.getByText('25%')).toBeTruthy()
    expect(screen.getByText('40%')).toBeTruthy()
  })

  it('refetches history when the range selector changes', async () => {
    const fetchMock = fetchRouter({
      'GET /api/resource-monitor-settings': () => jsonResponse(SETTINGS),
      'GET /api/resource-monitor-history?range=4h': () => jsonResponse(HISTORY_4H),
      'GET /api/resource-monitor-history?range=30m': () => jsonResponse(HISTORY_30M),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ResourceHistoryChartSection />)
    await waitFor(() => screen.getByText('15%'))

    fireEvent.click(screen.getByText('30 min'))

    await waitFor(() => screen.getByText('50%'))
    expect(fetchMock).toHaveBeenCalledWith('/api/resource-monitor-history?range=30m', expect.anything())
  })

  it('shows the no-data hint when there are no samples yet', async () => {
    vi.stubGlobal(
      'fetch',
      fetchRouter({
        'GET /api/resource-monitor-settings': () => jsonResponse(SETTINGS),
        'GET /api/resource-monitor-history?range=4h': () =>
          jsonResponse({ range_seconds: 14400, network_scale_bytes_per_sec: 0, points: [] }),
      }),
    )

    render(<ResourceHistoryChartSection />)

    await waitFor(() => screen.getByText(/No samples yet/))
  })
})
