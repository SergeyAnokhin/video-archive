import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { ResourceHistory, ResourceMonitorSettings } from '../types/api'
import { formatSize } from '../utils/format'
import './ResourceHistoryChartSection.css'

type RangeKey = '30m' | '4h' | '12h' | '24h'
const RANGE_KEYS: RangeKey[] = ['30m', '4h', '12h', '24h']

// Fixed, theme-independent series colors -- unlike the live gauge's
// green/yellow/red (severity) scale, these three lines are different
// *metrics*, not severity levels, so they need to stay visually distinct
// across all eight theme presets rather than tracking each theme's accent.
const SERIES_COLORS = { cpu: '#ff8a3d', memory: '#4f8cff', network: '#34d399' } as const

const CHART_WIDTH = 720
const CHART_HEIGHT = 200
const PADDING = { top: 12, right: 12, bottom: 22, left: 34 }
const INNER_WIDTH = CHART_WIDTH - PADDING.left - PADDING.right
const INNER_HEIGHT = CHART_HEIGHT - PADDING.top - PADDING.bottom
const Y_TICKS = [0, 25, 50, 75, 100]
const X_TICK_COUNT = 5

// A poll faster than this would just hammer the endpoint for no benefit --
// the chart is only ever as fresh as resource_monitor's own sample interval.
const MIN_POLL_MS = 5000

function yFor(percent: number): number {
  const clamped = Math.min(100, Math.max(0, percent))
  return PADDING.top + (1 - clamped / 100) * INNER_HEIGHT
}

/** Settings -> Performance CPU/memory/network history chart (chat request
 * 2026-07-25). Polls `GET /api/resource-monitor-history` at the same cadence
 * as resource_monitor's own log interval (`/api/resource-monitor-settings`)
 * -- there's no point sampling the chart faster than the backend samples
 * itself. CPU/memory are already 0-100 percentages of a natural ceiling;
 * network has none, so the backend normalizes it against the highest
 * throughput seen in the last 24h (`network_scale_bytes_per_sec`) regardless
 * of which range is currently displayed. */
export function ResourceHistoryChartSection() {
  const { t } = useTranslation()
  const [range, setRange] = useState<RangeKey>('4h')
  const [history, setHistory] = useState<ResourceHistory | null>(null)
  const [intervalSeconds, setIntervalSeconds] = useState(30)

  useEffect(() => {
    void (async () => {
      const settings = await tryApi<ResourceMonitorSettings>('/api/resource-monitor-settings')
      if (settings) setIntervalSeconds(settings.interval_seconds)
    })()
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      const data = await tryApi<ResourceHistory>(`/api/resource-monitor-history?range=${range}`)
      if (!cancelled && data) setHistory(data)
    }
    void load()
    const pollMs = Math.max(MIN_POLL_MS, intervalSeconds * 1000)
    const timer = window.setInterval(() => void load(), pollMs)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [range, intervalSeconds])

  const points = history?.points ?? []
  const minTs = points.length > 0 ? points[0].timestamp : 0
  const maxTs = points.length > 0 ? points[points.length - 1].timestamp : 0
  const span = maxTs - minTs || 1

  function xFor(timestamp: number): number {
    return PADDING.left + ((timestamp - minTs) / span) * INNER_WIDTH
  }

  function pathFor(key: 'cpu_percent' | 'memory_percent' | 'network_percent'): string {
    return points.map((p) => `${xFor(p.timestamp).toFixed(1)},${yFor(p[key]).toFixed(1)}`).join(' ')
  }

  const xTicks =
    points.length > 1
      ? Array.from({ length: X_TICK_COUNT }, (_, i) => minTs + (i / (X_TICK_COUNT - 1)) * span)
      : []

  const latest = points.length > 0 ? points[points.length - 1] : null
  const networkScaleText = history ? `${formatSize(Math.round(history.network_scale_bytes_per_sec))}` : '0 B'

  const legendItems: { key: 'cpu' | 'memory' | 'network'; label: string; value: number | null; tooltip?: string }[] = [
    { key: 'cpu', label: t('resourceHistoryChart.legendCpu'), value: latest?.cpu_percent ?? null },
    { key: 'memory', label: t('resourceHistoryChart.legendMemory'), value: latest?.memory_percent ?? null },
    {
      key: 'network',
      label: t('resourceHistoryChart.legendNetwork'),
      value: latest?.network_percent ?? null,
      tooltip: t('resourceHistoryChart.networkTooltip', { value: networkScaleText }),
    },
  ]

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('resourceHistoryChart.title')}</h3>
      <p className="settings-modal__hint">{t('resourceHistoryChart.hint')}</p>

      <div className="settings-modal__options" role="group" aria-label={t('resourceHistoryChart.rangeLabel')}>
        {RANGE_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            className="settings-modal__option"
            aria-pressed={range === key}
            onClick={() => setRange(key)}
          >
            {t(`resourceHistoryChart.range${key[0].toUpperCase()}${key.slice(1)}`)}
          </button>
        ))}
      </div>

      <div className="resource-history-chart">
        <div className="resource-history-chart__legend">
          {legendItems.map((item) => (
            <span key={item.key} className="resource-history-chart__legend-item" title={item.tooltip}>
              <span
                className="resource-history-chart__legend-swatch"
                style={{ background: SERIES_COLORS[item.key] }}
              />
              {item.label}
              {item.value !== null && (
                <span className="resource-history-chart__legend-value">{Math.round(item.value)}%</span>
              )}
            </span>
          ))}
        </div>

        {points.length === 0 ? (
          <p className="settings-modal__hint">{t('resourceHistoryChart.noData')}</p>
        ) : (
          <svg
            viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
            preserveAspectRatio="none"
            className="resource-history-chart__svg"
            role="img"
            aria-label={t('resourceHistoryChart.title')}
          >
            {Y_TICKS.map((tick) => (
              <g key={tick}>
                <line
                  x1={PADDING.left}
                  x2={CHART_WIDTH - PADDING.right}
                  y1={yFor(tick)}
                  y2={yFor(tick)}
                  className="resource-history-chart__gridline"
                />
                <text x={PADDING.left - 6} y={yFor(tick)} className="resource-history-chart__axis-label" textAnchor="end">
                  {tick}
                </text>
              </g>
            ))}

            {xTicks.map((tickTs) => (
              <text
                key={tickTs}
                x={xFor(tickTs)}
                y={CHART_HEIGHT - 4}
                className="resource-history-chart__axis-label"
                textAnchor="middle"
              >
                {new Date(tickTs * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </text>
            ))}

            {points.length > 1 && (
              <>
                <polyline points={pathFor('network_percent')} className="resource-history-chart__line" stroke={SERIES_COLORS.network} />
                <polyline points={pathFor('memory_percent')} className="resource-history-chart__line" stroke={SERIES_COLORS.memory} />
                <polyline points={pathFor('cpu_percent')} className="resource-history-chart__line" stroke={SERIES_COLORS.cpu} />
              </>
            )}
          </svg>
        )}
      </div>
    </section>
  )
}
