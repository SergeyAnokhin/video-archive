import { describe, expect, it } from 'vitest'
import { computeNetworkRate } from './backendStats'

describe('computeNetworkRate', () => {
  it('returns 0 with no previous sample (first poll)', () => {
    expect(computeNetworkRate(null, { bytes: 1000, timestampSeconds: 10 })).toBe(0)
  })

  it('computes bytes/sec between two samples', () => {
    const prev = { bytes: 1000, timestampSeconds: 10 }
    const curr = { bytes: 6000, timestampSeconds: 15 }
    expect(computeNetworkRate(prev, curr)).toBe(1000)
  })

  it('clamps to 0 when the counter goes backwards (backend restarted)', () => {
    const prev = { bytes: 6000, timestampSeconds: 10 }
    const curr = { bytes: 200, timestampSeconds: 15 }
    expect(computeNetworkRate(prev, curr)).toBe(0)
  })

  it('clamps to 0 when the elapsed time is not positive', () => {
    const prev = { bytes: 1000, timestampSeconds: 10 }
    const curr = { bytes: 2000, timestampSeconds: 10 }
    expect(computeNetworkRate(prev, curr)).toBe(0)
  })
})
