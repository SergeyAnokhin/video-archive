import { describe, expect, it } from 'vitest'
import { estimateEtaSeconds } from './eta'

describe('estimateEtaSeconds', () => {
  it('returns null with fewer than two samples', () => {
    expect(estimateEtaSeconds([], 0, 43)) .toBeNull()
    expect(estimateEtaSeconds([{ time: 0, done: 0 }], 0, 43)).toBeNull()
  })

  it('returns null when total is unknown or not yet positive', () => {
    const history = [
      { time: 0, done: 0 },
      { time: 10_000, done: 5 },
    ]
    expect(estimateEtaSeconds(history, 5, 0)).toBeNull()
    expect(estimateEtaSeconds(history, 5, -1)).toBeNull()
  })

  it('returns null when no progress was made across the window', () => {
    const history = [
      { time: 0, done: 5 },
      { time: 10_000, done: 5 },
    ]
    expect(estimateEtaSeconds(history, 5, 43)).toBeNull()
  })

  it('extrapolates remaining time from the rate between the first and last sample', () => {
    // 5 items done over 10 seconds -> 0.5 items/sec; 38 remaining -> 76 sec.
    const history = [
      { time: 0, done: 0 },
      { time: 10_000, done: 5 },
    ]
    expect(estimateEtaSeconds(history, 5, 43)).toBeCloseTo(76, 5)
  })

  it('only uses the first and last sample, ignoring the shape in between', () => {
    const history = [
      { time: 0, done: 0 },
      { time: 3_000, done: 1 },
      { time: 4_000, done: 4 },
      { time: 10_000, done: 5 },
    ]
    expect(estimateEtaSeconds(history, 5, 43)).toBeCloseTo(76, 5)
  })

  it('returns 0 once done reaches or exceeds total', () => {
    const history = [
      { time: 0, done: 40 },
      { time: 10_000, done: 43 },
    ]
    expect(estimateEtaSeconds(history, 43, 43)).toBe(0)
    expect(estimateEtaSeconds(history, 44, 43)).toBe(0)
  })
})
