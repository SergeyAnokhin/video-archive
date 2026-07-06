import { RotateCcw, ScrollText, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs } from '../context/JobsContext'
import type { JobStatus, JobSummary } from '../types/api'
import { LogViewerModal } from './LogViewerModal'
import './JobsModal.css'

interface JobsModalProps {
  onClose: () => void
}

const SECTION_ORDER: JobStatus[] = ['running', 'queued', 'failed', 'cancelled', 'completed']

export function JobsModal({ onClose }: JobsModalProps) {
  const { t } = useTranslation()
  const { jobs, refresh } = useJobs()
  const [logJobId, setLogJobId] = useState<string | null>(null)
  const [busyJobId, setBusyJobId] = useState<string | null>(null)

  async function handleCancel(jobId: string) {
    setBusyJobId(jobId)
    try {
      await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' })
      await refresh()
    } finally {
      setBusyJobId(null)
    }
  }

  async function handleRestart(jobId: string) {
    setBusyJobId(jobId)
    try {
      await fetch(`/api/jobs/${jobId}/restart`, { method: 'POST' })
      await refresh()
    } finally {
      setBusyJobId(null)
    }
  }

  async function handleRemove(jobId: string) {
    setBusyJobId(jobId)
    try {
      await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusyJobId(null)
    }
  }

  async function handleClearFinished() {
    await fetch('/api/jobs', { method: 'DELETE' })
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
              {sectionJobs.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  busy={busyJobId === job.id}
                  onCancel={() => handleCancel(job.id)}
                  onRestart={() => handleRestart(job.id)}
                  onRemove={() => handleRemove(job.id)}
                  onViewLog={() => setLogJobId(job.id)}
                />
              ))}
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
            {t('jobs.clearFinished')}
          </button>
        </div>
      </div>

      {logJobId !== null && (
        <LogViewerModal onClose={() => setLogJobId(null)} initialJobId={logJobId || null} />
      )}
    </div>
  )
}

interface JobRowProps {
  job: JobSummary
  busy: boolean
  onCancel: () => void
  onRestart: () => void
  onRemove: () => void
  onViewLog: () => void
}

function JobRow({ job, busy, onCancel, onRestart, onRemove, onViewLog }: JobRowProps) {
  const { t } = useTranslation()
  const canCancel = job.status === 'queued' || job.status === 'running'
  const canRestart = job.status === 'failed' || job.status === 'cancelled'
  const canRemove = job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled'

  return (
    <div className="jobs-modal__row">
      <div className="jobs-modal__row-info">
        <span className="jobs-modal__row-type">{t(`jobs.type.${job.job_type}`, job.job_type)}</span>
        <span className="jobs-modal__row-scope">{job.scope_ref ?? t('jobs.scopeWholeSource')}</span>
        {job.summary_message && (
          <span className="jobs-modal__row-message">{job.summary_message}</span>
        )}
      </div>
      <div className="jobs-modal__row-actions">
        <button
          type="button"
          className="jobs-modal__icon-btn"
          aria-label={t('logs.title')}
          title={t('logs.title')}
          onClick={onViewLog}
        >
          <ScrollText size={16} />
        </button>
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
  )
}
