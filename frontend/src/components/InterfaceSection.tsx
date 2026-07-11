import { useEffect, useState } from 'react'
import { Languages, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES } from '../i18n'
import { useInterfaceSettings } from '../context/InterfaceSettingsContext'
import { THEME_PRESETS } from '../types/api'
import { THEME_ICON } from '../themeIcons'
import type { SearchLimits } from '../types/api'
import { loadPreviewSampleFileIds } from '../utils/recentlyViewed'
import { DEFAULT_PREVIEW_PROFILE_A, previewFilterCss, type PreviewStyleProfile } from '../utils/previewStyle'

const SLIDER_FIELDS: { key: keyof PreviewStyleProfile; labelKey: string; min: number; max: number; unit: string }[] = [
  { key: 'saturation', labelKey: 'settings.previewSaturation', min: 0, max: 100, unit: '%' },
  { key: 'blur', labelKey: 'settings.previewBlur', min: 0, max: 20, unit: 'px' },
  { key: 'brightness', labelKey: 'settings.previewBrightness', min: 50, max: 150, unit: '%' },
  { key: 'contrast', labelKey: 'settings.previewContrast', min: 50, max: 150, unit: '%' },
  { key: 'sepia', labelKey: 'settings.previewSepia', min: 0, max: 100, unit: '%' },
  { key: 'hueRotate', labelKey: 'settings.previewHueRotate', min: 0, max: 360, unit: '°' },
]

function PreviewProfileEditor({
  titleKey,
  profile,
  onChange,
  sampleFileIds,
}: {
  titleKey: string
  profile: PreviewStyleProfile
  onChange: (next: PreviewStyleProfile) => void
  sampleFileIds: string[]
}) {
  const { t } = useTranslation()
  const filterCss = previewFilterCss(profile)

  return (
    <div className="settings-modal__preview-profile">
      <h4 className="settings-modal__subheading">{t(titleKey)}</h4>
      {sampleFileIds.length > 0 && (
        <div className="settings-modal__preview-sample-row">
          {sampleFileIds.map((id) => (
            <img
              key={id}
              src={`/api/files/${id}/preview.gif`}
              alt=""
              className="settings-modal__preview-sample"
              style={{ filter: filterCss }}
              onError={(event) => {
                event.currentTarget.style.visibility = 'hidden'
              }}
            />
          ))}
        </div>
      )}
      {SLIDER_FIELDS.map(({ key, labelKey, min, max, unit }) => {
        const neutral = DEFAULT_PREVIEW_PROFILE_A[key]
        return (
          <div className="settings-modal__field settings-modal__field--column" key={key}>
            <span className="settings-modal__field-label">{t(labelKey)}</span>
            <div className="settings-modal__slider-row">
              <input
                type="range"
                min={min}
                max={max}
                value={profile[key]}
                className="settings-modal__slider"
                aria-label={t(labelKey)}
                onChange={(event) => onChange({ ...profile, [key]: Number(event.target.value) })}
              />
              <span className="settings-modal__slider-value">
                {profile[key]}
                {unit}
              </span>
              <button
                type="button"
                className="settings-modal__option settings-modal__option--icon"
                onClick={() => onChange({ ...profile, [key]: neutral })}
                disabled={profile[key] === neutral}
                aria-label={t('settings.resetToDefault')}
                title={t('settings.resetToDefault')}
              >
                <RotateCcw size={14} />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

const SEARCH_LIMIT_FIELDS: { key: keyof SearchLimits; labelKey: string }[] = [
  { key: 'tags', labelKey: 'settings.searchTagLimit' },
  { key: 'files', labelKey: 'settings.searchFileLimit' },
  { key: 'dirs', labelKey: 'settings.searchDirLimit' },
]

export function InterfaceSection() {
  const { t } = useTranslation()
  const { language, setLanguage, theme, setTheme, previewProfiles, setPreviewProfile, searchLimits, setSearchLimits } =
    useInterfaceSettings()
  const [sampleFileIds, setSampleFileIds] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    void loadPreviewSampleFileIds().then((ids) => {
      if (!cancelled) setSampleFileIds(ids)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">
        {t('settings.interfaceSection')}
      </h3>
      <div className="settings-modal__field">
        <span className="settings-modal__field-label">
          {t('settings.language')}
        </span>
        <div
          className="settings-modal__options"
          role="group"
          aria-label={t('settings.language')}
        >
          {SUPPORTED_LANGUAGES.map((option) => (
            <button
              key={option}
              type="button"
              className="settings-modal__option"
              aria-pressed={language === option}
              onClick={() => setLanguage(option)}
            >
              <Languages size={14} /> {t(`language.${option}`)}
            </button>
          ))}
        </div>
      </div>
      <div className="settings-modal__field">
        <span className="settings-modal__field-label">
          {t('settings.theme')}
        </span>
        <div
          className="settings-modal__options"
          role="group"
          aria-label={t('settings.theme')}
        >
          {THEME_PRESETS.map((option) => {
            const Icon = THEME_ICON[option]
            return (
              <button
                key={option}
                type="button"
                className="settings-modal__option"
                aria-pressed={theme === option}
                onClick={() => setTheme(option)}
              >
                <span className="settings-modal__theme-swatch" data-theme={option} aria-hidden="true">
                  <span className="settings-modal__theme-swatch-dot" />
                  <span className="settings-modal__theme-swatch-dot settings-modal__theme-swatch-dot--2" />
                </span>
                <Icon size={14} /> {t(`theme.${option}`)}
              </button>
            )
          })}
        </div>
      </div>

      <h4 className="settings-modal__subheading">{t('settings.searchLimitsTitle')}</h4>
      <p className="settings-modal__hint">{t('settings.searchLimitsHint')}</p>
      <div className="settings-modal__row">
        {SEARCH_LIMIT_FIELDS.map(({ key, labelKey }) => (
          <label className="settings-modal__field settings-modal__field--column" key={key}>
            <span className="settings-modal__field-label">{t(labelKey)}</span>
            <input
              type="number"
              min={1}
              max={100}
              value={searchLimits[key]}
              onChange={(event) => {
                const parsed = Number(event.target.value)
                if (Number.isFinite(parsed) && parsed >= 1 && parsed <= 100) {
                  setSearchLimits({ ...searchLimits, [key]: Math.round(parsed) })
                }
              }}
            />
          </label>
        ))}
      </div>

      <p className="settings-modal__hint">{t('settings.previewStyleHint')}</p>
      <PreviewProfileEditor
        titleKey="settings.previewProfileA"
        profile={previewProfiles.a}
        onChange={(next) => setPreviewProfile('a', next)}
        sampleFileIds={sampleFileIds}
      />
      <PreviewProfileEditor
        titleKey="settings.previewProfileB"
        profile={previewProfiles.b}
        onChange={(next) => setPreviewProfile('b', next)}
        sampleFileIds={sampleFileIds}
      />
    </section>
  )
}
