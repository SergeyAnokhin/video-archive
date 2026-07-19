/** Cumulative-bytes sample used to derive a bytes/sec rate between two polls
 * of `/api/system/stats` (the backend only reports a running total, not a
 * rate -- see `system_stats.py`). */
export interface ByteSample {
  bytes: number
  timestampSeconds: number
}

/** Bytes/sec since `prev`, clamped to 0. Guards the two ways this goes
 * wrong: no `prev` yet (first poll), and the backend process restarting
 * between polls (its counter resets to 0, producing a negative delta). */
export function computeNetworkRate(prev: ByteSample | null, curr: ByteSample): number {
  if (!prev) return 0
  const deltaBytes = curr.bytes - prev.bytes
  const deltaSeconds = curr.timestampSeconds - prev.timestampSeconds
  if (deltaBytes <= 0 || deltaSeconds <= 0) return 0
  return deltaBytes / deltaSeconds
}
