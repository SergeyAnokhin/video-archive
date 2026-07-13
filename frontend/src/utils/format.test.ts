import { describe, expect, it } from 'vitest'
import { basename, formatBitrate, formatDuration, formatElapsed, formatElapsedCompact, formatSize } from './format'

const UNITS = { day: 'd', hour: 'h', minute: 'min', second: 'sec' }
const SHORT_UNITS = { day: 'd', hour: 'h', minute: 'm', second: 's' }

describe('formatSize', () => {
  it('keeps sub-kilobyte values in bytes', () => {
    expect(formatSize(0)).toBe('0 B')
    expect(formatSize(1023)).toBe('1023 B')
  })

  it('scales through KB/MB/GB/TB with one decimal', () => {
    expect(formatSize(1024)).toBe('1.0 KB')
    expect(formatSize(1536)).toBe('1.5 KB')
    expect(formatSize(1024 * 1024)).toBe('1.0 MB')
    expect(formatSize(3.4 * 1024 * 1024 * 1024)).toBe('3.4 GB')
    expect(formatSize(2 * 1024 ** 4)).toBe('2.0 TB')
  })

  it('caps at TB instead of inventing a bigger unit', () => {
    expect(formatSize(5000 * 1024 ** 4)).toBe('5000.0 TB')
  })
})

describe('formatBitrate', () => {
  it('renders sub-megabit rates in whole Kbps', () => {
    expect(formatBitrate(128_000)).toBe('128 Kbps')
    expect(formatBitrate(999_999)).toBe('1000 Kbps')
  })

  it('renders megabit rates with one decimal', () => {
    expect(formatBitrate(1_000_000)).toBe('1.0 Mbps')
    expect(formatBitrate(4_560_000)).toBe('4.6 Mbps')
  })
})

describe('formatDuration', () => {
  it('renders minutes:seconds below an hour', () => {
    expect(formatDuration(0)).toBe('0:00')
    expect(formatDuration(65)).toBe('1:05')
    expect(formatDuration(3599)).toBe('59:59')
  })

  it('adds an hours segment with zero-padded minutes from one hour up', () => {
    expect(formatDuration(3600)).toBe('1:00:00')
    expect(formatDuration(3661)).toBe('1:01:01')
  })

  it('rounds fractional seconds', () => {
    expect(formatDuration(89.6)).toBe('1:30')
  })
})

describe('formatElapsed', () => {
  it('renders seconds alone below a minute', () => {
    expect(formatElapsed(0, UNITS)).toBe('0 sec')
    expect(formatElapsed(45, UNITS)).toBe('45 sec')
  })

  it('renders minutes, dropping seconds when exact', () => {
    expect(formatElapsed(90, UNITS)).toBe('1 min 30 sec')
    expect(formatElapsed(120, UNITS)).toBe('2 min')
  })

  it('renders hours, dropping minutes when exact', () => {
    expect(formatElapsed(3661, UNITS)).toBe('1 h 1 min')
    expect(formatElapsed(7200, UNITS)).toBe('2 h')
  })

  it('renders days, dropping hours when exact, and never shows minutes/seconds', () => {
    expect(formatElapsed(86400, UNITS)).toBe('1 d')
    expect(formatElapsed(90000, UNITS)).toBe('1 d 1 h')
    expect(formatElapsed(90065, UNITS)).toBe('1 d 1 h')
  })

  it('rounds fractional seconds and clamps negatives to zero', () => {
    expect(formatElapsed(59.6, UNITS)).toBe('1 min')
    expect(formatElapsed(-5, UNITS)).toBe('0 sec')
  })
})

describe('formatElapsedCompact', () => {
  it('joins a number directly to its unit letter, no internal space', () => {
    expect(formatElapsedCompact(45, SHORT_UNITS)).toBe('45s')
    expect(formatElapsedCompact(90, SHORT_UNITS)).toBe('1m 30s')
    expect(formatElapsedCompact(3661, SHORT_UNITS)).toBe('1h 1m')
    expect(formatElapsedCompact(90000, SHORT_UNITS)).toBe('1d 1h')
  })

  it('still separates the two unit groups with a space', () => {
    expect(formatElapsedCompact(120, SHORT_UNITS)).toBe('2m')
  })
})

describe('basename', () => {
  it('returns the last segment of a forward-slash path', () => {
    expect(basename('Foscam/2026/categories/2_535728.mp4')).toBe('2_535728.mp4')
  })

  it('returns the last segment of a backslash path', () => {
    expect(basename('Foscam\\2026\\categories\\2_535728.mp4')).toBe('2_535728.mp4')
  })

  it('returns the input unchanged when there is no path separator', () => {
    expect(basename('2_535728.mp4')).toBe('2_535728.mp4')
  })
})
