import { Eye, EyeOff, ListChecks, Loader2, Menu, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { usePreviewVisibility } from '../context/PreviewVisibilityContext'
import { useJobs } from '../context/JobsContext'
import './TopBar.css'

interface TopBarProps {
  onMenuToggle: () => void
  onSettingsToggle: () => void
  onJobsToggle: () => void
}

export function TopBar({ onMenuToggle, onSettingsToggle, onJobsToggle }: TopBarProps) {
  const { t } = useTranslation()
  const { previewsVisible, toggle } = usePreviewVisibility()
  const { activeJob, activeJobItems } = useJobs()

  const previewToggleLabel = t(
    previewsVisible ? 'topBar.hidePreviews' : 'topBar.showPreviews',
  )

  const currentItem =
    [...activeJobItems].reverse().find((item) => item.status === 'running') ??
    [...activeJobItems].reverse().find((item) => item.status !== 'queued') ??
    null

  const activityLabel = activeJob
    ? t('jobs.indicatorTooltip', {
        jobType: t(`jobs.type.${activeJob.job_type}`, activeJob.job_type),
        current: currentItem?.item_key ?? activeJob.scope_ref ?? t('jobs.scopeWholeSource'),
      })
    : ''

  return (
    <header className="top-bar">
      <button
        type="button"
        className="top-bar__icon-btn top-bar__menu-toggle"
        aria-label={t('topBar.menuToggle')}
        onClick={onMenuToggle}
      >
        <Menu size={20} />
      </button>

      <span className="top-bar__title">{t('app.title')}</span>

      {activeJob && (
        <button
          type="button"
          className="top-bar__icon-btn top-bar__activity"
          aria-label={activityLabel}
          title={activityLabel}
          onClick={onJobsToggle}
        >
          <Loader2 size={20} className="top-bar__activity-spinner" />
        </button>
      )}

      <button
        type="button"
        className="top-bar__icon-btn"
        aria-label={t('topBar.jobsToggle')}
        title={t('topBar.jobsToggle')}
        onClick={onJobsToggle}
      >
        <ListChecks size={20} />
      </button>

      <button
        type="button"
        className="top-bar__icon-btn"
        aria-pressed={previewsVisible}
        aria-label={previewToggleLabel}
        title={previewToggleLabel}
        onClick={toggle}
      >
        {previewsVisible ? <Eye size={20} /> : <EyeOff size={20} />}
      </button>

      <button
        type="button"
        className="top-bar__icon-btn"
        aria-label={t('topBar.settingsToggle')}
        title={t('topBar.settingsToggle')}
        onClick={onSettingsToggle}
      >
        <Settings size={20} />
      </button>
    </header>
  )
}
