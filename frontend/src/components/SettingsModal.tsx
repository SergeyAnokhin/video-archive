import { X, HardDrive, Layers, Wand2, Images, PlayCircle, Tags, Bot, Archive, Palette, Cpu } from 'lucide-react'
import { useEffect, useState, type ComponentType } from 'react'
import { useTranslation } from 'react-i18next'
import { SourceSection } from './SourceSection'
import { SavedSourcesSection } from './SavedSourcesSection'
import { ConversionProfilesSection } from './ConversionProfilesSection'
import { PreviewSettingsSection } from './PreviewSettingsSection'
import { TaggingSettingsSection } from './TaggingSettingsSection'
import { ProviderSettingsSection } from './ProviderSettingsSection'
import { PlaybackSettingsSection } from './PlaybackSettingsSection'
import { BackupMaintenanceSection } from './BackupMaintenanceSection'
import { InterfaceSection } from './InterfaceSection'
import { PerformanceSettingsSection } from './PerformanceSettingsSection'
import './SettingsModal.css'

interface SettingsModalProps {
  onClose: () => void
}

type TabId =
  | 'source'
  | 'savedSources'
  | 'profiles'
  | 'preview'
  | 'playback'
  | 'tagging'
  | 'providers'
  | 'backup'
  | 'interface'
  | 'performance'

interface TabDef {
  id: TabId
  icon: ComponentType<{ size?: number }>
  labelKey: string
  Component: ComponentType
}

const TABS: TabDef[] = [
  { id: 'source', icon: HardDrive, labelKey: 'settings.sourceSection', Component: SourceSection },
  { id: 'savedSources', icon: Layers, labelKey: 'savedSources.title', Component: SavedSourcesSection },
  { id: 'profiles', icon: Wand2, labelKey: 'conversionProfiles.title', Component: ConversionProfilesSection },
  { id: 'preview', icon: Images, labelKey: 'previewSettings.title', Component: PreviewSettingsSection },
  { id: 'playback', icon: PlayCircle, labelKey: 'playbackSettings.title', Component: PlaybackSettingsSection },
  { id: 'tagging', icon: Tags, labelKey: 'tagging.title', Component: TaggingSettingsSection },
  { id: 'providers', icon: Bot, labelKey: 'providerSettings.title', Component: ProviderSettingsSection },
  { id: 'backup', icon: Archive, labelKey: 'backupMaintenance.title', Component: BackupMaintenanceSection },
  { id: 'performance', icon: Cpu, labelKey: 'performanceSettings.title', Component: PerformanceSettingsSection },
  { id: 'interface', icon: Palette, labelKey: 'settings.interfaceSection', Component: InterfaceSection },
]

export function SettingsModal({ onClose }: SettingsModalProps) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<TabId>('source')

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  const active = TABS.find((tab) => tab.id === activeTab) ?? TABS[0]
  const ActiveComponent = active.Component

  return (
    <div className="settings-modal-overlay" onClick={onClose}>
      <div
        className="settings-modal"
        role="dialog"
        aria-modal="true"
        aria-label={t('settings.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="settings-modal__header">
          <h2 className="settings-modal__title">{t('settings.title')}</h2>
          <button
            type="button"
            className="settings-modal__close"
            aria-label={t('settings.close')}
            title={t('settings.close')}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>

        <div className="settings-modal__body">
          <nav className="settings-modal__tabs" role="tablist" aria-label={t('settings.title')}>
            {TABS.map((tab) => {
              const Icon = tab.icon
              const label = t(tab.labelKey)
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab.id}
                  className="settings-modal__tab"
                  title={label}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <Icon size={18} />
                  <span className="settings-modal__tab-label">{label}</span>
                </button>
              )
            })}
          </nav>

          <div className="settings-modal__content" role="tabpanel">
            <ActiveComponent />
          </div>
        </div>
      </div>
    </div>
  )
}
