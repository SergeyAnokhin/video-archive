import { describe, expect, it } from 'vitest'
import { formatBitrate, formatDuration, formatSize } from './format'

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
