import { Eye, EyeOff, Menu, Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { usePreviewVisibility } from '../context/PreviewVisibilityContext'
import './TopBar.css'

interface TopBarProps {
  onMenuToggle: () => void
  onSettingsToggle: () => void
}

export function TopBar({ onMenuToggle, onSettingsToggle }: TopBarProps) {
  const { t } = useTranslation()
  const { previewsVisible, toggle } = usePreviewVisibility()

  const previewToggleLabel = t(
    previewsVisible ? 'topBar.hidePreviews' : 'topBar.showPreviews',
  )

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
