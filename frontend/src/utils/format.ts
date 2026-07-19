export function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`
}

export function formatBitrate(bitsPerSecond: number): string {
  if (bitsPerSecond < 1_000_000) {
    return `${(bitsPerSecond / 1000).toFixed(0)} Kbps`
  }
  return `${(bitsPerSecond / 1_000_000).toFixed(1)} Mbps`
}

export function formatDuration(seconds: number): string {
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

export interface DurationUnitLabels {
  day: string
  hour: string
  minute: string
  second: string
}

/** Human-readable elapsed/remaining time, e.g. "2 ч 15 мин", "45 мин 30 сек", "3 дн". */
export function formatElapsed(seconds: number, units: DurationUnitLabels): string {
  const total = Math.max(0, Math.round(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60

  if (days > 0) {
    return hours > 0 ? `${days} ${units.day} ${hours} ${units.hour}` : `${days} ${units.day}`
  }
  if (hours > 0) {
    return minutes > 0 ? `${hours} ${units.hour} ${minutes} ${units.minute}` : `${hours} ${units.hour}`
  }
  if (minutes > 0) {
    return secs > 0 ? `${minutes} ${units.minute} ${secs} ${units.second}` : `${minutes} ${units.minute}`
  }
  return `${secs} ${units.second}`
}

/** Compact elapsed/remaining time for tight card layouts, e.g. "4m 22s", "2h 15m", "3d" —
 * no space between a number and its unit letter, unlike `formatElapsed`. */
export function formatElapsedCompact(seconds: number, units: DurationUnitLabels): string {
  const total = Math.max(0, Math.round(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60

  if (days > 0) {
    return hours > 0 ? `${days}${units.day} ${hours}${units.hour}` : `${days}${units.day}`
  }
  if (hours > 0) {
    return minutes > 0 ? `${hours}${units.hour} ${minutes}${units.minute}` : `${hours}${units.hour}`
  }
  if (minutes > 0) {
    return secs > 0 ? `${minutes}${units.minute} ${secs}${units.second}` : `${minutes}${units.minute}`
  }
  return `${secs}${units.second}`
}

/** Last path segment of a `/`- or `\`-separated relative path, e.g. "a/b/c.mp4" -> "c.mp4". */
export function basename(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts[parts.length - 1] || path
}

/** Containing directory of a `/`- or `\`-separated relative path, e.g. "a/b/c.mp4" -> "a/b"; "c.mp4" -> "". */
export function dirname(path: string): string {
  const parts = path.split(/[\\/]/)
  return parts.slice(0, -1).join('/')
}
