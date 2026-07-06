import { X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { LogEvent } from '../types/api'
import './LogViewerModal.css'

interface LogViewerModalProps {
  onClose: () => void
  initialJobId?: string | null
}

const LEVELS = ['debug', 'info', 'warning', 'error'] as const
const MAX_EVENTS = 500

export function LogViewerModal({ onClose, initialJobId = null }: LogViewerModalProps) {
  const { t } = useTranslation()
  const [jobIdFilter, setJobIdFilter] = useState(initialJobId ?? '')
  const [fileIdFilter, setFileIdFilter] = useState('')
  const [levelFilter, setLevelFilter] = useState('')
  const [events, setEvents] = useState<LogEvent[]>([])
  const listRef = useRef<HTMLDivElement | null>(null)

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
    let cancelled = false
    setEvents([])

    const params = new URLSearchParams()
    if (jobIdFilter) params.set('job_id', jobIdFilter)
    if (fileIdFilter) params.set('file_id', fileIdFilter)
    if (levelFilter) params.set('level', levelFilter)

    async function loadInitial() {
      try {
        const res = await fetch(`/api/logs?${params.toString()}&limit=200`)
        if (!res.ok) return
        const data: { events: LogEvent[] } = await res.json()
        if (!cancelled) {
          setEvents(data.events)
        }
      } catch {
        // The stream below will still deliver new events even if this backfill fails.
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
    <div className="log-viewer-overlay" onClick={onClose}>
      <div
        className="log-viewer"
        role="dialog"
        aria-modal="true"
        aria-label={t('logs.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="log-viewer__header">
          <h2 className="log-viewer__title">{t('logs.title')}</h2>
          <button
            type="button"
            className="log-viewer__close"
            aria-label={t('logs.close')}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>

        <div className="log-viewer__filters">
          <input
            className="log-viewer__filter-input"
            placeholder={t('logs.filterJob')}
            value={jobIdFilter}
            onChange={(event) => setJobIdFilter(event.target.value)}
          />
          <input
            className="log-viewer__filter-input"
            placeholder={t('logs.filterFile')}
            value={fileIdFilter}
            onChange={(event) => setFileIdFilter(event.target.value)}
          />
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
          {events.map((event) => (
            <div key={event.id} className={`log-viewer__row log-viewer__row--${event.level}`}>
              <span className="log-viewer__time">
                {new Date(event.created_at).toLocaleTimeString()}
              </span>
              <span className="log-viewer__level">{event.level}</span>
              <span className="log-viewer__message">{event.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
