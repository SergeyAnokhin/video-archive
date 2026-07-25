import { Check, Copy, Download, Maximize2, Minimize2, Trash2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tryApi } from '../api/client'
import type { LogEvent, LogFile } from '../types/api'
import './LogViewerModal.css'

interface LogViewerModalProps {
  onClose: () => void
  initialJobId?: string | null
}

const LEVELS = ['debug', 'info', 'warning', 'error'] as const
const MAX_EVENTS = 500

// Cycled by file_index so each file gets a consistent, visually distinct
// badge color even without clicking to filter. Text color is derived from
// luminance so it stays readable against whichever color lands.
const FILE_BADGE_COLORS = [
  '#ef4444',
  '#f97316',
  '#eab308',
  '#22c55e',
  '#14b8a6',
  '#3b82f6',
  '#8b5cf6',
  '#ec4899',
]

function fileBadgeTextColor(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.6 ? '#000000' : '#ffffff'
}

function fileBadgeColors(fileIndex: number): { background: string; color: string } {
  const background = FILE_BADGE_COLORS[fileIndex % FILE_BADGE_COLORS.length]
  return { background, color: fileBadgeTextColor(background) }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function LogFilesPanel() {
  const { t } = useTranslation()
  const [files, setFiles] = useState<LogFile[] | null>(null)
  const [busyName, setBusyName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function loadFiles() {
    const data = await tryApi<{ files: LogFile[] }>('/api/log-files')
    if (data) setFiles(data.files)
  }

  useEffect(() => {
    void loadFiles()
  }, [])

  async function handleDelete(file: LogFile) {
    if (!window.confirm(t('logs.confirmDelete', { name: file.name }))) return
    setBusyName(file.name)
    setError(null)
    try {
      await api(`/api/log-files/${encodeURIComponent(file.name)}`, { method: 'DELETE' })
      await loadFiles()
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? t('logs.deleteActiveFileError') : t('logs.deleteError'))
    } finally {
      setBusyName(null)
    }
  }

  return (
    <div className="log-viewer__files">
      {files === null && <p className="log-viewer__empty">{t('logs.filesLoading')}</p>}
      {files !== null && files.length === 0 && <p className="log-viewer__empty">{t('logs.filesEmpty')}</p>}
      {files !== null &&
        files.map((file) => (
          <div key={file.name} className="log-viewer__file-row">
            <span className="log-viewer__file-name">{file.name}</span>
            <span className="log-viewer__file-meta">
              {formatFileSize(file.size_bytes)} · {new Date(file.modified_at * 1000).toLocaleString()}
            </span>
            <a
              className="log-viewer__file-download"
              href={`/api/log-files/${encodeURIComponent(file.name)}`}
              download={file.name}
              title={t('logs.download')}
            >
              <Download size={14} />
            </a>
            <button
              type="button"
              className="log-viewer__file-delete"
              onClick={() => void handleDelete(file)}
              disabled={busyName === file.name}
              aria-label={t('logs.delete')}
              title={t('logs.delete')}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      {error && <p className="log-viewer__file-error">{error}</p>}
    </div>
  )
}

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
  const [viewMode, setViewMode] = useState<'events' | 'files'>('events')
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

        <div className="log-viewer__view-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'events'}
            className={`log-viewer__view-tab${viewMode === 'events' ? ' log-viewer__view-tab--active' : ''}`}
            onClick={() => setViewMode('events')}
          >
            {t('logs.viewEvents')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'files'}
            className={`log-viewer__view-tab${viewMode === 'files' ? ' log-viewer__view-tab--active' : ''}`}
            onClick={() => setViewMode('files')}
          >
            {t('logs.viewFiles')}
          </button>
        </div>

        {viewMode === 'events' && (
          <>
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
                        style={fileBadgeColors(fileIndex)}
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
          </>
        )}

        {viewMode === 'files' && <LogFilesPanel />}
      </div>
    </div>
  )
}
