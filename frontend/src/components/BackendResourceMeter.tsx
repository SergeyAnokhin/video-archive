import { useState, type ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { Cpu, MemoryStick, Wifi } from 'lucide-react'
import type { BackendStats } from '../hooks/useBackendStats'
import { formatSize } from '../utils/format'
import './BackendResourceMeter.css'

type MeterMode = 'numbers' | 'rings' | 'bars' | 'glow'
const MODES: MeterMode[] = ['numbers', 'rings', 'bars', 'glow']
const STORAGE_KEY = 'backendResourceMeter.mode'

function loadInitialMode(): MeterMode {
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return (MODES as string[]).includes(stored ?? '') ? (stored as MeterMode) : 'numbers'
}

/** Green/yellow/red threshold for a 0-100 percent gauge (CPU, memory). */
function levelColor(percent: number): string {
  if (percent > 85) return 'var(--color-danger)'
  if (percent > 60) return 'var(--color-warning)'
  return 'var(--color-success)'
}

// SMB read throughput has no natural 100% ceiling -- this is purely a visual
// scale for the ring/bar fill (the exact rate is always in the tooltip).
const NETWORK_SCALE_BYTES_PER_SEC = 5 * 1024 * 1024

interface MeterItem {
  key: string
  Icon: typeof Cpu
  percent: number
  valueText: string
  tooltip: string
}

interface BackendResourceMeterProps {
  stats: BackendStats
}

/** Compact CPU/memory/network(SMB) gauge next to the status dot (chat
 * request 2026-07-19). Click cycles through four display modes -- numbers
 * with thin bars, ring gauges, vertical bar gauges, glowing icons --
 * persisted in localStorage (survives across app restarts, same as the chat
 * request 2026-07-19 follow-up asked for "cookies"). The icon-only modes
 * carry the exact value in each item's `title` tooltip. */
export function BackendResourceMeter({ stats }: BackendResourceMeterProps) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<MeterMode>(loadInitialMode)

  function cycleMode() {
    const next = MODES[(MODES.indexOf(mode) + 1) % MODES.length]
    setMode(next)
    window.localStorage.setItem(STORAGE_KEY, next)
  }

  // Clamp once and reuse everywhere: `stats.cpuPercent`/`memoryPercent` can
  // briefly tick a hair past 100 depending on sampling timing, and the text
  // must always agree with the bar/ring/vbar fill next to it.
  const cpuPercent = Math.min(100, Math.round(stats.cpuPercent))

  const items: MeterItem[] = [
    {
      key: 'cpu',
      Icon: Cpu,
      percent: cpuPercent,
      valueText: `${cpuPercent}%`,
      tooltip: t('backendMeter.cpuValue', { value: cpuPercent }),
    },
    {
      key: 'memory',
      Icon: MemoryStick,
      percent: Math.min(100, stats.memoryPercent),
      valueText: formatSize(stats.memoryRssBytes),
      tooltip: t('backendMeter.memoryValue', { value: formatSize(stats.memoryRssBytes) }),
    },
    {
      key: 'network',
      Icon: Wifi,
      percent: Math.min(100, (stats.networkBytesPerSec / NETWORK_SCALE_BYTES_PER_SEC) * 100),
      valueText: `${formatSize(stats.networkBytesPerSec)}/s`,
      tooltip: t('backendMeter.networkValue', { value: formatSize(stats.networkBytesPerSec) }),
    },
  ]

  return (
    <button
      type="button"
      className={`backend-meter backend-meter--${mode}`}
      onClick={cycleMode}
      aria-label={t('backendMeter.toggleView')}
    >
      {items.map((item) => {
        const ItemView = MODE_VIEWS[mode]
        return <ItemView key={item.key} item={item} />
      })}
    </button>
  )
}

function NumberRow({ item }: { item: MeterItem }) {
  return (
    <span className="backend-meter__row" title={item.tooltip}>
      <item.Icon size={11} className="backend-meter__icon" />
      <span className="backend-meter__track">
        <span className="backend-meter__fill" style={{ width: `${item.percent}%`, background: levelColor(item.percent) }} />
      </span>
      <span className="backend-meter__value">{item.valueText}</span>
    </span>
  )
}

// Rings/bars encode usage as a level color (green/yellow/red), which can't
// also tell CPU/memory/network apart -- a small muted glyph does that job
// instead, same icon as the numbers-mode row, kept out of the level-color
// language so the two aren't read as the same signal.
function RingGauge({ item }: { item: MeterItem }) {
  const radius = 7
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - item.percent / 100)
  return (
    <span className="backend-meter__gauge backend-meter__gauge--ring" title={item.tooltip}>
      <svg width={18} height={18} viewBox="0 0 18 18" className="backend-meter__ring">
        <circle cx={9} cy={9} r={radius} className="backend-meter__ring-track" />
        <circle
          cx={9}
          cy={9}
          r={radius}
          className="backend-meter__ring-fill"
          stroke={levelColor(item.percent)}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <item.Icon size={8} className="backend-meter__gauge-icon backend-meter__gauge-icon--ring" />
    </span>
  )
}

function BarGauge({ item }: { item: MeterItem }) {
  return (
    <span className="backend-meter__gauge backend-meter__gauge--bar" title={item.tooltip}>
      <item.Icon size={8} className="backend-meter__gauge-icon" />
      <span className="backend-meter__vbar-track">
        <span
          className="backend-meter__vbar-fill"
          style={{ height: `${item.percent}%`, background: levelColor(item.percent) }}
        />
      </span>
    </span>
  )
}

// 0% still reads as a dim-but-visible icon rather than fully invisible --
// only the top of the range should look "lit up".
const GLOW_MIN_OPACITY = 0.35

function GlowIcon({ item }: { item: MeterItem }) {
  const color = levelColor(item.percent)
  const opacity = GLOW_MIN_OPACITY + (item.percent / 100) * (1 - GLOW_MIN_OPACITY)
  const glowRadius = 2 + (item.percent / 100) * 5
  return (
    <span className="backend-meter__gauge" title={item.tooltip}>
      <item.Icon
        size={14}
        className="backend-meter__glow-icon"
        style={{ color, opacity, filter: `drop-shadow(0 0 ${glowRadius}px ${color})` }}
      />
    </span>
  )
}

const MODE_VIEWS: Record<MeterMode, ComponentType<{ item: MeterItem }>> = {
  numbers: NumberRow,
  rings: RingGauge,
  bars: BarGauge,
  glow: GlowIcon,
}
