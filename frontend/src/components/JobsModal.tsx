import {
  Ban,
  CheckCircle2,
  Clock,
  Eraser,
  Hourglass,
  Layers,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  ScrollText,
  Timer,
  Trash2,
  X,
  XCircle,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import { useJobs } from '../context/JobsContext'
import type { JobItem, JobStatus, JobSummary } from '../types/api'
import { estimateEtaSeconds, type ProgressSample } from '../utils/eta'
import { basename, formatElapsed, formatElapsedCompact, type DurationUnitLabels } from '../utils/format'
import { BatchSubmissionsModal } from './BatchSubmissionsModal'
import { LogViewerModal } from './LogViewerModal'
import './JobsModal.css'

interface JobsModalProps {
  onClose: () => void
}

const SECTION_ORDER: JobStatus[] = ['running', 'paused', 'queued', 'failed', 'cancelled', 'completed']
const EMPTY_ITEMS: JobItem[] = []
const DONE_ITEM_STATUSES = new Set(['completed', 'failed', 'skipped', 'cancelled'])
const ETA_WINDOW_MS = 5 * 60 * 1000

// Mirrors `PAUSABLE_JOB_TYPES` in `backend/app/jobs/service.py`: only job
// types with a per-item loop can honor a pause request between items --
// `optimize_db`/`backup`/`restore` run one atomic action with no checkpoint.
const PAUSABLE_JOB_TYPES = new Set(['rescan', 'convert', 'preview', 'tag', 'cleanup'])

// Prefer an icon over a text label for status (per CLAUDE.md UI conventions):
// the shape + color read at a glance, the full word is still available via `title` on hover.
const STATUS_ICON: Record<JobStatus, LucideIcon> = {
  queued: Clock,
  running: Loader2,
  paused: Pause,
  completed: CheckCircle2,
  failed: XCircle,
  cancelled: Ban,
}

export function JobsModal({ onClose }: JobsModalProps) {
  const { t } = useTranslation()
  const { jobs, jobItemsById, refresh } = useJobs()
  const [logJobId, setLogJobId] = useState<string | null>(null)
  const [busyJobId, setBusyJobId] = useState<string | null>(null)
  const [showBatchSubmissions, setShowBatchSubmissions] = useState(false)

  async function handleCancel(jobId: string) {
    setBusyJobId(jobId)
    try {
      await tryApi(`/api/jobs/${jobId}/cancel`, { method: 'POST' })
      await refresh()
    } finally {
      setBusyJobId(null)
    }
  }

  async function handlePause(jobId: string) {
    setBusyJobId(jobId)
    try {
      await tryApi(`/api/jobs/${jobId}/pause`, { method: 'POST' })
      await refresh()
    } finally {
      setBusyJobId(null)
    }
  }

  async function handleResume(jobId: string) {
    setBusyJobId(jobId)
    try {
      await tryApi(`/api/jobs/${jobId}/resume`, { method: 'POST' })
      await refresh()
    } finally {
      setBusyJobId(null)
    }
  }

  async function handleRestart(jobId: string) {
    setBusyJobId(jobId)
    try {
      await tryApi(`/api/jobs/${jobId}/restart`, { method: 'POST' })
      await refresh()
    } finally {
      setBusyJobId(null)
    }
  }

  async function handleRemove(jobId: string) {
    setBusyJobId(jobId)
    try {
      await tryApi(`/api/jobs/${jobId}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusyJobId(null)
    }
  }

  async function handleClearFinished() {
    await tryApi('/api/jobs', { method: 'DELETE' })
    await refresh()
  }

  const hasFinished = jobs.some(
    (job) => job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled',
  )

  return (
    <div className="jobs-modal-overlay" onClick={onClose}>
      <div
        className="jobs-modal"
        role="dialog"
        aria-modal="true"
        aria-label={t('jobs.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="jobs-modal__header">
          <h2 className="jobs-modal__title">{t('jobs.title')}</h2>
          <div className="jobs-modal__header-actions">
            <button
              type="button"
              className="jobs-modal__icon-btn"
              aria-label={t('batchSubmissions.title')}
              title={t('batchSubmissions.title')}
              onClick={() => setShowBatchSubmissions(true)}
            >
              <Layers size={18} />
            </button>
            <button
              type="button"
              className="jobs-modal__icon-btn"
              aria-label={t('logs.title')}
              title={t('logs.title')}
              onClick={() => setLogJobId('')}
            >
              <ScrollText size={18} />
            </button>
            <button
              type="button"
              className="jobs-modal__close"
              aria-label={t('jobs.close')}
              onClick={onClose}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {jobs.length === 0 && <p className="jobs-modal__empty">{t('jobs.empty')}</p>}

        {SECTION_ORDER.map((status) => {
          const sectionJobs = jobs.filter((job) => job.status === status)
          if (sectionJobs.length === 0) {
            return null
          }
          return (
            <section key={status} className="jobs-modal__section">
              <h3 className="jobs-modal__section-title">
                {t(`jobs.section.${status}`)} ({sectionJobs.length})
              </h3>
              <div className="jobs-modal__section-cards">
                {sectionJobs.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    items={jobItemsById[job.id] ?? EMPTY_ITEMS}
                    busy={busyJobId === job.id}
                    onCancel={() => handleCancel(job.id)}
                    onPause={() => handlePause(job.id)}
                    onResume={() => handleResume(job.id)}
                    onRestart={() => handleRestart(job.id)}
                    onRemove={() => handleRemove(job.id)}
                    onViewLog={() => setLogJobId(job.id)}
                  />
                ))}
              </div>
            </section>
          )
        })}

        <div className="jobs-modal__footer">
          <button
            type="button"
            className="jobs-modal__option"
            onClick={handleClearFinished}
            disabled={!hasFinished}
          >
            <Eraser size={14} /> {t('jobs.clearFinished')}
          </button>
        </div>
      </div>

      {logJobId !== null && (
        <LogViewerModal onClose={() => setLogJobId(null)} initialJobId={logJobId || null} />
      )}
      {showBatchSubmissions && <BatchSubmissionsModal onClose={() => setShowBatchSubmissions(false)} />}
    </div>
  )
}

/** Tracks (time, doneCount) samples for the last `ETA_WINDOW_MS` while a job
 * is running, so `estimateEtaSeconds()` can extrapolate from the recent
 * completion rate instead of the average over the job's whole lifetime. */
function useEtaSeconds(jobId: string, isRunning: boolean, done: number, total: number | null): number | null {
  const historyRef = useRef<ProgressSample[]>([])
  const jobIdRef = useRef(jobId)

  if (jobIdRef.current !== jobId) {
    jobIdRef.current = jobId
    historyRef.current = []
  }

  useEffect(() => {
    if (!isRunning) return
    const now = Date.now()
    const history = historyRef.current
    const lastEntry = history[history.length - 1]
    if (!lastEntry || lastEntry.done !== done) {
      history.push({ time: now, done })
    }
    const cutoff = now - ETA_WINDOW_MS
    while (history.length > 1 && history[0].time < cutoff) {
      history.shift()
    }
  }, [isRunning, done])

  if (!isRunning || total === null) return null
  return estimateEtaSeconds(historyRef.current, done, total)
}

/** Elapsed time since `startedAt`, refreshed every second while `live` is true. */
function useElapsedSeconds(startedAt: string | null, live: boolean): number | null {
  const [, setTick] = useState(0)

  useEffect(() => {
    if (!live) return
    const timer = window.setInterval(() => setTick((tick) => tick + 1), 1000)
    return () => window.clearInterval(timer)
  }, [live])

  if (!startedAt) return null
  return (Date.now() - new Date(startedAt).getTime()) / 1000
}

interface JobRowProps {
  job: JobSummary
  items: JobItem[]
  busy: boolean
  onCancel: () => void
  onPause: () => void
  onResume: () => void
  onRestart: () => void
  onRemove: () => void
  onViewLog: () => void
}

function JobRow({ job, items, busy, onCancel, onPause, onResume, onRestart, onRemove, onViewLog }: JobRowProps) {
  const { t } = useTranslation()
  const canCancel = job.status === 'queued' || job.status === 'running' || job.status === 'paused'
  const canPause =
    (job.status === 'queued' || job.status === 'running') && PAUSABLE_JOB_TYPES.has(job.job_type)
  const canResume = job.status === 'paused'
  const canRestart = job.status === 'failed' || job.status === 'cancelled'
  const canRemove = job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled'
  const isRunning = job.status === 'running'

  const units: DurationUnitLabels = {
    day: t('jobs.unit.day'),
    hour: t('jobs.unit.hour'),
    minute: t('jobs.unit.minute'),
    second: t('jobs.unit.second'),
  }
  const compactUnits: DurationUnitLabels = {
    day: t('jobs.unitShort.day'),
    hour: t('jobs.unitShort.hour'),
    minute: t('jobs.unitShort.minute'),
    second: t('jobs.unitShort.second'),
  }

  const done = items.filter((item) => DONE_ITEM_STATUSES.has(item.status)).length
  const total = job.total_items
  const currentItem = isRunning
    ? [...items].reverse().find((item) => item.status === 'running')
    : undefined
  const progressPct = total && total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null

  const etaSeconds = useEtaSeconds(job.id, isRunning, done, total)
  const runningElapsedSeconds = useElapsedSeconds(job.started_at, isRunning)

  const finishedElapsedSeconds =
    job.started_at && job.finished_at
      ? (new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000
      : null

  const finishedAtLabel = job.finished_at
    ? new Date(job.finished_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : null

  const clickableForLog = job.status === 'running' || job.status === 'queued' || job.status === 'paused'
  const StatusIcon = STATUS_ICON[job.status]
  const statusLabel = t(`jobs.section.${job.status}`)

  return (
    <div
      className={`jobs-modal__card jobs-modal__card--${job.status}`}
      onClick={clickableForLog ? onViewLog : undefined}
      role={clickableForLog ? 'button' : undefined}
      tabIndex={clickableForLog ? 0 : undefined}
    >
      <div className="jobs-modal__card-header">
        <div className="jobs-modal__card-heading">
          <span
            className={`jobs-modal__status-icon jobs-modal__status-icon--${job.status}`}
            title={statusLabel}
            aria-label={statusLabel}
          >
            <StatusIcon size={14} />
          </span>
          <span className="jobs-modal__row-type">{t(`jobs.type.${job.job_type}`, job.job_type)}</span>
        </div>
        <div className="jobs-modal__row-actions" onClick={(event) => event.stopPropagation()}>
          <button
            type="button"
            className="jobs-modal__icon-btn"
            aria-label={t('logs.title')}
            title={t('logs.title')}
            onClick={onViewLog}
          >
            <ScrollText size={16} />
          </button>
          {canPause && (
            <button
              type="button"
              className="jobs-modal__icon-btn"
              aria-label={t('jobs.pause')}
              title={t('jobs.pause')}
              onClick={onPause}
              disabled={busy}
            >
              <Pause size={16} />
            </button>
          )}
          {canResume && (
            <button
              type="button"
              className="jobs-modal__icon-btn"
              aria-label={t('jobs.resume')}
              title={t('jobs.resume')}
              onClick={onResume}
              disabled={busy}
            >
              <Play size={16} />
            </button>
          )}
          {canCancel && (
            <button
              type="button"
              className="jobs-modal__icon-btn"
              aria-label={t('jobs.cancel')}
              title={t('jobs.cancel')}
              onClick={onCancel}
              disabled={busy}
            >
              <X size={16} />
            </button>
          )}
          {canRestart && (
            <button
              type="button"
              className="jobs-modal__icon-btn"
              aria-label={t('jobs.restart')}
              title={t('jobs.restart')}
              onClick={onRestart}
              disabled={busy}
            >
              <RotateCcw size={16} />
            </button>
          )}
          {canRemove && (
            <button
              type="button"
              className="jobs-modal__icon-btn jobs-modal__icon-btn--danger"
              aria-label={t('jobs.remove')}
              title={t('jobs.remove')}
              onClick={onRemove}
              disabled={busy}
            >
              <Trash2 size={16} />
            </button>
          )}
        </div>
      </div>

      <div className="jobs-modal__row-scope">{job.scope_ref ?? t('jobs.scopeWholeSource')}</div>

      {job.summary_message && <div className="jobs-modal__row-message">{job.summary_message}</div>}

      {job.failed_item_count > 0 && (
        <div className="jobs-modal__error-count">
          {t('jobs.progress.errors', { count: job.failed_item_count })}
        </div>
      )}

      {currentItem && (
        <div className="jobs-modal__row-message" title={currentItem.item_key ?? undefined}>
          {t('jobs.progress.current', {
            name: currentItem.item_key ? basename(currentItem.item_key) : (currentItem.file_id ?? '…'),
          })}
        </div>
      )}

      {progressPct !== null && (isRunning || job.status === 'paused') && (
        <div className="jobs-modal__progress">
          <div className="jobs-modal__progress-track">
            <div className="jobs-modal__progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <span className="jobs-modal__progress-count">{t('jobs.progress.count', { done, total })}</span>
        </div>
      )}

      {isRunning && (
        <div className="jobs-modal__meta">
          {runningElapsedSeconds !== null && (
            <span title={t('jobs.progress.elapsed', { time: formatElapsed(runningElapsedSeconds, units) })}>
              <Timer size={12} /> {formatElapsedCompact(runningElapsedSeconds, compactUnits)}
            </span>
          )}
          {etaSeconds !== null && (
            <span title={t('jobs.progress.eta', { time: formatElapsed(etaSeconds, units) })}>
              <Hourglass size={12} /> {formatElapsedCompact(etaSeconds, compactUnits)}
            </span>
          )}
        </div>
      )}

      {!isRunning && (finishedElapsedSeconds !== null || finishedAtLabel) && (
        <div className="jobs-modal__meta">
          {finishedElapsedSeconds !== null && (
            <span>{t('jobs.progress.took', { time: formatElapsed(finishedElapsedSeconds, units) })}</span>
          )}
          {finishedAtLabel && <span>{t('jobs.progress.finishedAt', { time: finishedAtLabel })}</span>}
        </div>
      )}
    </div>
  )
}
