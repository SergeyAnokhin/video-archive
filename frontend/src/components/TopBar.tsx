import { Eye, EyeOff, ListChecks, Menu, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { usePreviewVisibility } from '../context/PreviewVisibilityContext'
import { useInterfaceSettings } from '../context/InterfaceSettingsContext'
import { useJobs } from '../context/JobsContext'
import { LibrarySearchBox } from './LibrarySearchBox'
import type { ActiveSearch } from '../utils/searchQuery'
import { THEME_PRESETS } from '../types/api'
import { THEME_ICON } from '../themeIcons'
import { BackendHealthWidget } from './BackendHealthWidget'
import './TopBar.css'

interface TopBarProps {
  onMenuToggle: () => void
  onSettingsToggle: () => void
  onJobsToggle: () => void
  activeSearch: ActiveSearch | null
  onSearch: (search: ActiveSearch) => void
  onClearSearch: () => void
  onOpenDirectory: (path: string) => void
}

export function TopBar({
  onMenuToggle,
  onSettingsToggle,
  onJobsToggle,
  activeSearch,
  onSearch,
  onClearSearch,
  onOpenDirectory,
}: TopBarProps) {
  const { t } = useTranslation()
  const { previewsVisible, toggle } = usePreviewVisibility()
  const { theme, setTheme } = useInterfaceSettings()
  const { jobs, activeJob, activeJobItems } = useJobs()
  const nextTheme = THEME_PRESETS[(THEME_PRESETS.indexOf(theme) + 1) % THEME_PRESETS.length]
  const ThemeIcon = THEME_ICON[theme]
  const themeToggleLabel = t('topBar.switchTheme', { theme: t(`theme.${nextTheme}`) })

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

  // Merged jobs-icon state (chat request): a running/queued job pulses the
  // icon with a slow glow, and any failed job (not just one interrupted by a
  // backend restart -- that finer distinction lives only on the job's own
  // row in JobsModal) rings it red, so a failure is noticeable without
  // opening the modal. Both can apply at once.
  const failedCount = jobs.filter((job) => job.status === 'failed').length
  const hasFailedJobs = failedCount > 0
  const jobsToggleLabel = hasFailedJobs
    ? t('jobs.failedBadge', { count: failedCount })
    : activeJob
      ? activityLabel
      : t('topBar.jobsToggle')
  const jobsToggleClassName = [
    'top-bar__icon-btn',
    'top-bar__jobs-toggle',
    activeJob ? 'top-bar__jobs-toggle--running' : '',
    hasFailedJobs ? 'top-bar__jobs-toggle--failed' : '',
  ]
    .filter(Boolean)
    .join(' ')

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
      <BackendHealthWidget />

      <div className="top-bar__search-slot">
        <LibrarySearchBox
          activeSearch={activeSearch}
          onSearch={onSearch}
          onClear={onClearSearch}
          onOpenDirectory={onOpenDirectory}
        />
      </div>

      <div className="top-bar__actions">
        <button
          type="button"
          className={jobsToggleClassName}
          aria-label={jobsToggleLabel}
          title={jobsToggleLabel}
          onClick={onJobsToggle}
        >
          <ListChecks size={20} />
          {hasFailedJobs && (
            <span className="top-bar__jobs-toggle-badge" aria-hidden="true">
              {failedCount > 9 ? '9+' : failedCount}
            </span>
          )}
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
          aria-label={themeToggleLabel}
          title={themeToggleLabel}
          onClick={() => setTheme(nextTheme)}
        >
          <ThemeIcon size={20} />
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
      </div>
    </header>
  )
}
