export interface ProgressSample {
  time: number
  done: number
}

/**
 * Estimates remaining seconds from the completion rate between the oldest
 * and newest sample in `history` (the caller keeps only samples from the
 * window it wants the rate measured over, e.g. the last 5 minutes).
 * Returns null when there isn't enough signal yet to extrapolate a rate.
 */
export function estimateEtaSeconds(
  history: ProgressSample[],
  done: number,
  total: number,
): number | null {
  if (total <= 0) return null
  if (history.length < 2) return null

  const first = history[0]
  const last = history[history.length - 1]
  const elapsedMs = last.time - first.time
  const deltaDone = last.done - first.done
  if (deltaDone <= 0 || elapsedMs <= 0) return null

  const remaining = total - done
  if (remaining <= 0) return 0

  const rate = deltaDone / (elapsedMs / 1000)
  return remaining / rate
}
