import { Eye, EyeOff, ListChecks, Loader2, Menu, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { usePreviewVisibility } from '../context/PreviewVisibilityContext'
import { useInterfaceSettings } from '../context/InterfaceSettingsContext'
import { useJobs } from '../context/JobsContext'
import { LibrarySearchBox } from './LibrarySearchBox'
import type { ActiveSearch } from '../utils/searchQuery'
import { THEME_PRESETS } from '../types/api'
import { THEME_ICON } from '../themeIcons'
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
  const { activeJob, activeJobItems } = useJobs()
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

      <div className="top-bar__search-slot">
        <LibrarySearchBox
          activeSearch={activeSearch}
          onSearch={onSearch}
          onClear={onClearSearch}
          onOpenDirectory={onOpenDirectory}
        />
      </div>

      <div className="top-bar__actions">
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
