import { Dices, Eye, EyeOff, ListChecks, Loader2, Menu, Palette, Settings, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { usePreviewVisibility } from '../context/PreviewVisibilityContext'
import { useInterfaceSettings } from '../context/InterfaceSettingsContext'
import { useJobs } from '../context/JobsContext'
import { LibrarySearchBox, type ActiveSearch } from './LibrarySearchBox'
import type { ThemePreset } from '../types/api'
import './TopBar.css'

interface TopBarProps {
  onMenuToggle: () => void
  onSettingsToggle: () => void
  onJobsToggle: () => void
  onSearch: (search: ActiveSearch) => void
  onClearSearch: () => void
}

const THEME_CYCLE: ThemePreset[] = ['strict', 'playful', 'casino']
const THEME_ICON: Record<ThemePreset, typeof Palette> = {
  strict: Palette,
  playful: Sparkles,
  casino: Dices,
}

export function TopBar({ onMenuToggle, onSettingsToggle, onJobsToggle, onSearch, onClearSearch }: TopBarProps) {
  const { t } = useTranslation()
  const { previewsVisible, toggle } = usePreviewVisibility()
  const { theme, setTheme } = useInterfaceSettings()
  const { activeJob, activeJobItems } = useJobs()
  const nextTheme = THEME_CYCLE[(THEME_CYCLE.indexOf(theme) + 1) % THEME_CYCLE.length]
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
        <LibrarySearchBox onSearch={onSearch} onClear={onClearSearch} />
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
