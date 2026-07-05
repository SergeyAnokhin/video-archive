import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { TopBar } from './TopBar'
import { SettingsModal } from './SettingsModal'
import './AppLayout.css'

interface AppLayoutProps {
  children: ReactNode
}

export function AppLayout({ children }: AppLayoutProps) {
  const { t } = useTranslation()
  const [navOpen, setNavOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <div className="app-shell">
      <TopBar
        onMenuToggle={() => setNavOpen((open) => !open)}
        onSettingsToggle={() => setSettingsOpen((open) => !open)}
      />
      <div className="app-body">
        <nav
          className={`app-nav${navOpen ? ' app-nav--open' : ''}`}
          aria-label={t('sidebar.title')}
        >
          <h2 className="app-nav__title">{t('sidebar.title')}</h2>
          <p className="app-nav__placeholder">{t('sidebar.placeholder')}</p>
        </nav>

        {navOpen && (
          <button
            type="button"
            className="app-nav-backdrop"
            aria-label={t('topBar.menuToggle')}
            onClick={() => setNavOpen(false)}
          />
        )}

        <main className="app-main">{children}</main>
      </div>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  )
}
