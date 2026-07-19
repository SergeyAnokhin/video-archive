import { Settings } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TopBar } from './TopBar'
import { SettingsModal } from './SettingsModal'
import { JobsModal } from './JobsModal'
import { DirectoryTree } from './DirectoryTree'
import { LibraryView } from './LibraryView'
import { BackendStatusPanel } from './BackendStatusPanel'
import type { ActiveSearch } from '../utils/searchQuery'
import { useSource } from '../context/SourceContext'
import './AppLayout.css'

export function AppLayout() {
  const { t } = useTranslation()
  const { source, loading } = useSource()
  const [navOpen, setNavOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [jobsOpen, setJobsOpen] = useState(false)
  const [selectedPath, setSelectedPath] = useState('')
  const [activeSearch, setActiveSearch] = useState<ActiveSearch | null>(null)

  function handleSelectPath(path: string) {
    setSelectedPath(path)
    setNavOpen(false)
  }

  return (
    <div className="app-shell">
      <TopBar
        onMenuToggle={() => setNavOpen((open) => !open)}
        onSettingsToggle={() => setSettingsOpen((open) => !open)}
        onJobsToggle={() => setJobsOpen((open) => !open)}
        activeSearch={activeSearch}
        onSearch={setActiveSearch}
        onClearSearch={() => setActiveSearch(null)}
        onOpenDirectory={handleSelectPath}
      />
      <div className="app-body">
        <nav
          className={`app-nav${navOpen ? ' app-nav--open' : ''}`}
          aria-label={t('sidebar.title')}
        >
          <h2 className="app-nav__title">{t('sidebar.title')}</h2>
          {source ? (
            <DirectoryTree selectedPath={selectedPath} onSelect={handleSelectPath} />
          ) : (
            <p className="app-nav__placeholder">{t('sidebar.noSource')}</p>
          )}
        </nav>

        {navOpen && (
          <button
            type="button"
            className="app-nav-backdrop"
            aria-label={t('topBar.menuToggle')}
            onClick={() => setNavOpen(false)}
          />
        )}

        <main className="app-main">
          {!loading && !source && (
            <div className="app-main__empty-state">
              <p>{t('library.noSource')}</p>
              <button type="button" onClick={() => setSettingsOpen(true)}>
                <Settings size={14} /> {t('topBar.settingsToggle')}
              </button>
              <BackendStatusPanel />
            </div>
          )}
          {source && (
            <LibraryView
              path={selectedPath}
              onNavigate={setSelectedPath}
              activeSearch={activeSearch}
              onSearch={setActiveSearch}
              onClearSearch={() => setActiveSearch(null)}
            />
          )}
        </main>
      </div>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
      {jobsOpen && (
        <JobsModal onClose={() => setJobsOpen(false)} onNavigate={handleSelectPath} />
      )}
    </div>
  )
}
