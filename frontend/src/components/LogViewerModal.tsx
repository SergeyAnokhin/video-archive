import { Check, Copy, Maximize2, Minimize2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { LogEvent } from '../types/api'
import './LogViewerModal.css'

interface LogViewerModalProps {
  onClose: () => void
  initialJobId?: string | null
}

const LEVELS = ['debug', 'info', 'warning', 'error'] as const
const MAX_EVENTS = 500

// `service.log_event()` (backend) prepends this to the message text itself
// so it also shows up in the console/copy-all output; stripped back off
// here since the Log Viewer renders the same number as its own clickable
// badge instead (`payload.file_index`). Not anchored to the start of the
// string: the backend also prepends a per-event-type emoji *after* this
// prefix (e.g. "⏭️ [#1] Skipped ..."), which would otherwise push `[#N]`
// past position 0 and make an anchored match silently fail.
const FILE_INDEX_PREFIX = /\[#\d+\]\s*/

function stripFileIndexPrefix(message: string): string {
  return message.replace(FILE_INDEX_PREFIX, '')
}

function formatElapsed(createdAt: string, baselineMs: number | null): string {
  if (baselineMs === null) return new Date(createdAt).toLocaleTimeString()
  const totalSeconds = Math.max(0, Math.floor((new Date(createdAt).getTime() - baselineMs) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function LogViewerModal({ onClose, initialJobId = null }: LogViewerModalProps) {
  const { t } = useTranslation()
  const [jobIdFilter, setJobIdFilter] = useState(initialJobId ?? '')
  const [fileIdFilter, setFileIdFilter] = useState('')
  const [levelFilter, setLevelFilter] = useState('')
  const [events, setEvents] = useState<LogEvent[]>([])
  const [copied, setCopied] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const listRef = useRef<HTMLDivElement | null>(null)
  const baselineMs = events.length > 0 ? new Date(events[0].created_at).getTime() : null

  async function handleCopyAll() {
    if (events.length === 0) return
    const text = events
      .map((event) => `${event.created_at} [${event.level.toUpperCase()}] ${event.message}`)
      .join('\n')
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  useEffect(() => {
    if (!isFullscreen) {
      return
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        // Capture phase + stopPropagation so the first Escape only exits
        // fullscreen; the bubble-phase listener above still closes the
        // modal on a second Escape (same pattern as TaggingSettingsSection).
        event.stopPropagation()
        setIsFullscreen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [isFullscreen])

  useEffect(() => {
    let cancelled = false
    setEvents([])

    const params = new URLSearchParams()
    if (jobIdFilter) params.set('job_id', jobIdFilter)
    if (fileIdFilter) params.set('file_id', fileIdFilter)
    if (levelFilter) params.set('level', levelFilter)

    async function loadInitial() {
      // The stream below will still deliver new events even if this backfill fails.
      const data = await tryApi<{ events: LogEvent[] }>(`/api/logs?${params.toString()}&limit=200`)
      if (data && !cancelled) {
        setEvents(data.events)
      }
    }
    void loadInitial()

    const source = new EventSource(`/api/logs/stream?${params.toString()}`)
    source.addEventListener('log', (event) => {
      const parsed: LogEvent = JSON.parse((event as MessageEvent).data)
      setEvents((prev) => [...prev, parsed].slice(-MAX_EVENTS))
    })

    return () => {
      cancelled = true
      source.close()
    }
  }, [jobIdFilter, fileIdFilter, levelFilter])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [events])

  return (
    <div className={`log-viewer-overlay${isFullscreen ? ' log-viewer-overlay--fullscreen' : ''}`} onClick={onClose}>
      <div
        className={`log-viewer${isFullscreen ? ' log-viewer--fullscreen' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={t('logs.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="log-viewer__header">
          <h2 className="log-viewer__title">{t('logs.title')}</h2>
          <div className="log-viewer__header-actions">
            <button
              type="button"
              className="log-viewer__copy"
              onClick={() => void handleCopyAll()}
              disabled={events.length === 0}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? t('logs.copied') : t('logs.copyAll')}
            </button>
            <button
              type="button"
              className="log-viewer__fullscreen"
              aria-label={isFullscreen ? t('logs.exitFullscreen') : t('logs.enterFullscreen')}
              title={isFullscreen ? t('logs.exitFullscreen') : t('logs.enterFullscreen')}
              onClick={() => setIsFullscreen((prev) => !prev)}
            >
              {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
            <button
              type="button"
              className="log-viewer__close"
              aria-label={t('logs.close')}
              onClick={onClose}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="log-viewer__filters">
          <input
            className="log-viewer__filter-input"
            placeholder={t('logs.filterJob')}
            value={jobIdFilter}
            onChange={(event) => setJobIdFilter(event.target.value)}
          />
          <div className="log-viewer__filter-with-clear">
            <input
              className="log-viewer__filter-input"
              placeholder={t('logs.filterFile')}
              value={fileIdFilter}
              onChange={(event) => setFileIdFilter(event.target.value)}
            />
            {fileIdFilter && (
              <button
                type="button"
                className="log-viewer__filter-clear"
                aria-label={t('logs.clearFilter')}
                title={t('logs.clearFilter')}
                onClick={() => setFileIdFilter('')}
              >
                <X size={12} />
              </button>
            )}
          </div>
          <select
            className="log-viewer__filter-select"
            value={levelFilter}
            onChange={(event) => setLevelFilter(event.target.value)}
          >
            <option value="">{t('logs.filterLevelAll')}</option>
            {LEVELS.map((level) => (
              <option key={level} value={level}>
                {t(`logs.level.${level}`)}
              </option>
            ))}
          </select>
        </div>

        <div className="log-viewer__list" ref={listRef}>
          {events.length === 0 && <p className="log-viewer__empty">{t('logs.empty')}</p>}
          {events.map((event) => {
            const fileIndex = typeof event.payload?.file_index === 'number' ? event.payload.file_index : null
            const isActiveFileFilter = fileIndex !== null && fileIdFilter === event.file_id
            return (
              <div key={event.id} className={`log-viewer__row log-viewer__row--${event.level}`}>
                <span
                  className="log-viewer__time"
                  title={`${new Date(event.created_at).toLocaleString()} · ${event.level.toUpperCase()}`}
                >
                  {formatElapsed(event.created_at, baselineMs)}
                </span>
                {fileIndex !== null && (
                  <button
                    type="button"
                    className={`log-viewer__file-badge${isActiveFileFilter ? ' log-viewer__file-badge--active' : ''}`}
                    title={t('logs.filterByFile')}
                    onClick={() => setFileIdFilter(isActiveFileFilter ? '' : (event.file_id ?? ''))}
                  >
                    #{fileIndex}
                  </button>
                )}
                <span className="log-viewer__message">{stripFileIndexPrefix(event.message)}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
