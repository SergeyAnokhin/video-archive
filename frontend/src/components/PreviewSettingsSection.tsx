import { Copy, Eraser, FolderOpen, Grid2x2, Grid3x3, LayoutGrid, Save, Square, Star, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, ApiError, tryApi } from '../api/client'
import type {
  AnimatedSourceMode,
  AnimatedTransition,
  AspectRatioMode,
  EnlargedTile,
  FrameSeekMode,
  LayoutTile,
  PreviewLayoutPreset,
  PreviewSettings,
  TimelineFlow,
} from '../types/api'
import { buildOccupancy, cellsOf, computeTilesLocal, fillAll } from '../utils/layoutGeometry'
import { LayoutCanvas } from './LayoutCanvas'
import './PreviewSettingsSection.css'

const ASPECT_RATIOS: AspectRatioMode[] = ['standard', 'phone-portrait', 'phone-landscape', 'ultra-wide', 'custom']
const QUICK_SLOT_NAMES = ['Quick 1', 'Quick 2', 'Quick 3']
const ANIMATED_SOURCE_MODES: AnimatedSourceMode[] = ['frame', 'clip']
const ANIMATED_TRANSITIONS: AnimatedTransition[] = ['cut', 'crossfade']
const FRAME_SEEK_MODES: FrameSeekMode[] = ['keyframe', 'accurate']

function effectiveAspectRatio(settings: PreviewSettings): number {
  switch (settings.aspect_ratio) {
    case 'phone-portrait':
      return 9 / 19.5
    case 'phone-landscape':
      return 19.5 / 9
    case 'ultra-wide':
      return 21 / 9
    case 'custom':
      return (settings.aspect_ratio_custom_width || 1) / (settings.aspect_ratio_custom_height || 1)
    default:
      return 4 / 3
  }
}

export function PreviewSettingsSection() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<'collage' | 'animated'>('collage')
  const [presets, setPresets] = useState<PreviewLayoutPreset[]>([])
  const [settings, setSettings] = useState<PreviewSettings | null>(null)
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null)

  const [gridRows, setGridRows] = useState(4)
  const [gridCols, setGridCols] = useState(4)
  const [enlarged, setEnlarged] = useState<EnlargedTile[]>([])
  const [timelineFlow, setTimelineFlow] = useState<TimelineFlow>('row')
  const [identityDiversity, setIdentityDiversity] = useState(true)
  const [brush, setBrush] = useState<'small' | 2 | 3>(2)

  const [tiles, setTiles] = useState<LayoutTile[]>([])
  const [frameCount, setFrameCount] = useState(0)
  const [layoutError, setLayoutError] = useState<string | null>(null)

  const [presetName, setPresetName] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const refreshPresets = useCallback(async () => {
    const data = await tryApi<{ presets: PreviewLayoutPreset[] }>('/api/preview-layouts')
    if (data) {
      setPresets(data.presets)
    }
  }, [])

  useEffect(() => {
    void refreshPresets()
    void (async () => {
      const loaded = await tryApi<PreviewSettings>('/api/preview-settings')
      if (loaded) {
        setSettings(loaded)
      }
    })()
  }, [refreshPresets])

  function loadPreset(preset: PreviewLayoutPreset) {
    setSelectedPresetId(preset.id)
    setGridRows(preset.grid_rows)
    setGridCols(preset.grid_cols)
    setEnlarged(preset.layout_definition)
    setTimelineFlow(preset.timeline_flow)
    setIdentityDiversity(preset.identity_diversity_enabled)
    setPresetName(preset.name)
  }

  useEffect(() => {
    if (presets.length > 0 && selectedPresetId === null) {
      loadPreset(presets.find((preset) => preset.is_default) ?? presets[0])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presets])

  // Recompute canonical tile geometry from the backend whenever the editable
  // geometry changes (single source of truth with the backend's grid rules).
  useEffect(() => {
    let cancelled = false
    async function run() {
      try {
        let data: { tiles: LayoutTile[]; frame_count: number }
        try {
          data = await api<{ tiles: LayoutTile[]; frame_count: number }>('/api/preview-layouts/preview', {
            method: 'POST',
            body: {
              grid_rows: gridRows,
              grid_cols: gridCols,
              layout_definition: enlarged,
              timeline_flow: timelineFlow,
              identity_diversity_enabled: identityDiversity,
            },
          })
        } catch (err) {
          if (!cancelled) {
            const detailMessage =
              err instanceof ApiError
                ? (err.detail as { error?: { message?: string } } | null)?.error?.message
                : undefined
            setLayoutError(detailMessage ?? t('previewSettings.layoutInvalid'))
          }
          return
        }
        if (!cancelled) {
          setTiles(data.tiles)
          setFrameCount(data.frame_count)
          setLayoutError(null)
        }
      } catch {
        // Network hiccup: keep the last known geometry rather than clearing the canvas.
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [gridRows, gridCols, enlarged, timelineFlow, identityDiversity, t])

  function handleCellClick(row: number, col: number) {
    if (brush === 'small') {
      setEnlarged((current) => current.filter((tile) => !cellsOf(tile).some(([r, c]) => r === row && c === col)))
      return
    }
    const span = brush
    if (row + span > gridRows || col + span > gridCols) {
      return
    }
    const occupancy = buildOccupancy(gridRows, gridCols, enlarged)
    for (let r = row; r < row + span; r++) {
      for (let c = col; c < col + span; c++) {
        if (occupancy[r][c]) {
          return
        }
      }
    }
    setEnlarged((current) => [...current, { row, col, span }])
  }

  function handleFillAll() {
    setEnlarged(fillAll(gridRows, gridCols, brush === 'small' ? 2 : brush))
  }

  function handleClearAll() {
    setEnlarged([])
  }

  async function persistPreset(name: string, presetId: string | null) {
    const body = {
      name,
      grid_rows: gridRows,
      grid_cols: gridCols,
      timeline_flow: timelineFlow,
      identity_diversity_enabled: identityDiversity,
      layout_definition: enlarged,
    }
    const url = presetId ? `/api/preview-layouts/${presetId}` : '/api/preview-layouts'
    return await api<PreviewLayoutPreset>(url, {
      method: presetId ? 'PUT' : 'POST',
      body,
    })
  }

  async function handleSavePreset(asNew: boolean) {
    setSaving(true)
    setSaveError(null)
    try {
      const existing = !asNew ? presets.find((preset) => preset.id === selectedPresetId) : null
      const editingBuiltin = Boolean(existing?.is_builtin)
      const saved = await persistPreset(presetName, existing && !editingBuiltin ? existing.id : null)
      await refreshPresets()
      setSelectedPresetId(saved.id)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveToSlot(slotIndex: number) {
    const slotName = QUICK_SLOT_NAMES[slotIndex]
    const existingSlot = presets.find((preset) => preset.name === slotName && !preset.is_builtin)
    await persistPreset(slotName, existingSlot?.id ?? null)
    await refreshPresets()
  }

  async function handleDeletePreset(preset: PreviewLayoutPreset) {
    await tryApi(`/api/preview-layouts/${preset.id}`, { method: 'DELETE' })
    await refreshPresets()
    if (selectedPresetId === preset.id) {
      setSelectedPresetId(null)
    }
  }

  async function handleSetDefault(preset: PreviewLayoutPreset) {
    await tryApi(`/api/preview-layouts/${preset.id}`, {
      method: 'PUT',
      body: { ...preset, is_default: true },
    })
    await refreshPresets()
  }

  async function updateSettings(patch: Partial<PreviewSettings>) {
    if (!settings) {
      return
    }
    const merged = { ...settings, ...patch }
    setSettings(merged)
    const saved = await tryApi<PreviewSettings>('/api/preview-settings', {
      method: 'PUT',
      body: merged,
    })
    if (saved) {
      setSettings(saved)
    }
  }

  const quickSlots = QUICK_SLOT_NAMES.map((name) => presets.find((preset) => preset.name === name && !preset.is_builtin))
  const selectedPreset = presets.find((preset) => preset.id === selectedPresetId) ?? null

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('previewSettings.title')}</h3>

      <div
        className="settings-modal__options settings-modal__options--segmented"
        role="tablist"
        aria-label={t('previewSettings.title')}
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'collage'}
          className="settings-modal__option"
          onClick={() => setActiveTab('collage')}
        >
          {t('previewSettings.tabCollage')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'animated'}
          className="settings-modal__option"
          onClick={() => setActiveTab('animated')}
        >
          {t('previewSettings.tabAnimated')}
        </button>
      </div>

      {activeTab === 'collage' && settings && (
        <>
          <label className="settings-modal__label">
            {t('previewSettings.aspectRatio')}
            <select
              className="settings-modal__input"
              value={settings.aspect_ratio}
              onChange={(event) => void updateSettings({ aspect_ratio: event.target.value as AspectRatioMode })}
            >
              {ASPECT_RATIOS.map((ratio) => (
                <option key={ratio} value={ratio}>
                  {t(`previewSettings.aspectRatioOption.${ratio}`)}
                </option>
              ))}
            </select>
          </label>

          {settings.aspect_ratio === 'custom' && (
            <div className="preview-settings__custom-ratio">
              <input
                type="number"
                min={1}
                className="settings-modal__input"
                value={settings.aspect_ratio_custom_width ?? 16}
                onChange={(event) => void updateSettings({ aspect_ratio_custom_width: Number(event.target.value) })}
              />
              <span>:</span>
              <input
                type="number"
                min={1}
                className="settings-modal__input"
                value={settings.aspect_ratio_custom_height ?? 9}
                onChange={(event) => void updateSettings({ aspect_ratio_custom_height: Number(event.target.value) })}
              />
            </div>
          )}
        </>
      )}

      {activeTab === 'animated' && settings && (
        <>
          <p className="settings-modal__hint">{t('previewSettings.animatedIntro')}</p>

          <label className="settings-modal__label">
            {t('previewSettings.frameSeekMode')}
            <select
              className="settings-modal__input"
              value={settings.frame_seek_mode}
              onChange={(event) => void updateSettings({ frame_seek_mode: event.target.value as FrameSeekMode })}
            >
              {FRAME_SEEK_MODES.map((mode) => (
                <option key={mode} value={mode}>
                  {t(`previewSettings.frameSeekModeOption.${mode}`)}
                </option>
              ))}
            </select>
          </label>
          <p className="settings-modal__hint">{t('previewSettings.frameSeekModeHint')}</p>

          <div className="settings-modal__row">
            <label className="settings-modal__label">
              {t('previewSettings.folderFrameCount')}
              <input
                type="number"
                min={1}
                max={20}
                className="settings-modal__input"
                value={settings.folder_preview_frame_count}
                onChange={(event) => void updateSettings({ folder_preview_frame_count: Number(event.target.value) })}
              />
            </label>

            <label className="settings-modal__label">
              {t('previewSettings.gifMaxWidth')}
              <input
                type="number"
                min={120}
                max={1920}
                step={20}
                className="settings-modal__input"
                value={settings.gif_max_width}
                onChange={(event) => void updateSettings({ gif_max_width: Number(event.target.value) })}
              />
            </label>

            <label className="settings-modal__label">
              {t('previewSettings.gifColors')}
              <input
                type="number"
                min={8}
                max={256}
                className="settings-modal__input"
                value={settings.gif_colors}
                onChange={(event) => void updateSettings({ gif_colors: Number(event.target.value) })}
              />
            </label>
          </div>

          <div className="settings-modal__row">
            <label className="settings-modal__label">
              {t('previewSettings.animatedSourceMode')}
              <select
                className="settings-modal__input"
                value={settings.animated_source_mode}
                onChange={(event) =>
                  void updateSettings({ animated_source_mode: event.target.value as AnimatedSourceMode })
                }
              >
                {ANIMATED_SOURCE_MODES.map((mode) => (
                  <option key={mode} value={mode}>
                    {t(`previewSettings.animatedSourceModeOption.${mode}`)}
                  </option>
                ))}
              </select>
            </label>

            <label className="settings-modal__label">
              {t(
                settings.animated_source_mode === 'clip'
                  ? 'previewSettings.animatedSegmentSecondsClip'
                  : 'previewSettings.animatedSegmentSeconds'
              )}
              <input
                type="number"
                min={0.1}
                max={5}
                step={0.1}
                className="settings-modal__input"
                value={settings.animated_segment_seconds}
                onChange={(event) => void updateSettings({ animated_segment_seconds: Number(event.target.value) })}
              />
            </label>

            <label className="settings-modal__label">
              {t('previewSettings.animatedTransition')}
              <select
                className="settings-modal__input"
                value={settings.animated_transition}
                onChange={(event) =>
                  void updateSettings({ animated_transition: event.target.value as AnimatedTransition })
                }
              >
                {ANIMATED_TRANSITIONS.map((transition) => (
                  <option key={transition} value={transition}>
                    {t(`previewSettings.animatedTransitionOption.${transition}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </>
      )}

      {activeTab === 'collage' && (
      <>
      <div className="preview-settings__toolbar">
        <div className="settings-modal__options" role="group" aria-label={t('previewSettings.brush')}>
          <button
            type="button"
            className="settings-modal__option settings-modal__option--icon"
            aria-pressed={brush === 'small'}
            onClick={() => setBrush('small')}
            aria-label={t('previewSettings.brushSmall')}
            title={t('previewSettings.brushSmall')}
          >
            <Square size={14} />
          </button>
          <button
            type="button"
            className="settings-modal__option settings-modal__option--icon"
            aria-pressed={brush === 2}
            onClick={() => setBrush(2)}
            aria-label={t('previewSettings.brushEnlarged2')}
            title={t('previewSettings.brushEnlarged2')}
          >
            <Grid2x2 size={14} />
          </button>
          <button
            type="button"
            className="settings-modal__option settings-modal__option--icon"
            aria-pressed={brush === 3}
            onClick={() => setBrush(3)}
            aria-label={t('previewSettings.brushEnlarged3')}
            title={t('previewSettings.brushEnlarged3')}
          >
            <Grid3x3 size={14} />
          </button>
        </div>
        <div className="settings-modal__actions">
          <button type="button" className="settings-modal__option" onClick={handleFillAll}>
            <LayoutGrid size={14} /> {t('previewSettings.fillAll')}
          </button>
          <button type="button" className="settings-modal__option" onClick={handleClearAll}>
            <Eraser size={14} /> {t('previewSettings.clearAll')}
          </button>
        </div>
      </div>

      <div className="preview-settings__grid-dims">
        <label className="settings-modal__label">
          {t('previewSettings.gridRows')}
          <input
            type="number"
            min={2}
            max={8}
            className="settings-modal__input"
            value={gridRows}
            onChange={(event) => setGridRows(Number(event.target.value))}
          />
        </label>
        <label className="settings-modal__label">
          {t('previewSettings.gridCols')}
          <input
            type="number"
            min={2}
            max={8}
            className="settings-modal__input"
            value={gridCols}
            onChange={(event) => setGridCols(Number(event.target.value))}
          />
        </label>
      </div>

      <label className="settings-modal__label">
        {t('previewSettings.timelineFlow')}
        <select
          className="settings-modal__input"
          value={timelineFlow}
          onChange={(event) => setTimelineFlow(event.target.value as TimelineFlow)}
        >
          <option value="row">{t('previewSettings.timelineFlowRow')}</option>
          <option value="column">{t('previewSettings.timelineFlowColumn')}</option>
          <option value="shuffle">{t('previewSettings.timelineFlowShuffle')}</option>
        </select>
      </label>

      <label className="settings-modal__field">
        <span className="settings-modal__field-label">{t('previewSettings.identityDiversity')}</span>
        <input
          type="checkbox"
          checked={identityDiversity}
          onChange={(event) => setIdentityDiversity(event.target.checked)}
        />
      </label>

      {layoutError && <p className="settings-modal__hint settings-modal__hint--error">{layoutError}</p>}
      {!layoutError && <p className="settings-modal__hint">{t('previewSettings.frameCount', { count: frameCount })}</p>}

      <LayoutCanvas
        tiles={tiles}
        gridRows={gridRows}
        gridCols={gridCols}
        aspectRatio={settings ? effectiveAspectRatio(settings) : 4 / 3}
        caption={t('previewSettings.captionSample')}
        onCellClick={handleCellClick}
      />

      <div className="preview-settings__presets">
        <h4 className="settings-modal__section-title">{t('previewSettings.presetGallery')}</h4>
        <div className="preview-settings__preset-list">
          {presets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className="preview-settings__preset-card"
              aria-pressed={selectedPresetId === preset.id}
              onClick={() => loadPreset(preset)}
            >
              <LayoutCanvas
                mini
                tiles={computeTilesLocal(preset.grid_rows, preset.grid_cols, preset.layout_definition)}
                gridRows={preset.grid_rows}
                gridCols={preset.grid_cols}
                aspectRatio={1}
              />
              <span>{preset.name}</span>
              {preset.is_default && <span className="conversion-profile-row__badge">{t('conversionProfiles.default')}</span>}
            </button>
          ))}
        </div>

        {selectedPreset && (
          <div className="settings-modal__actions">
            {!selectedPreset.is_default && (
              <button
                type="button"
                className="settings-modal__option settings-modal__option--icon"
                onClick={() => handleSetDefault(selectedPreset)}
                aria-label={t('conversionProfiles.markDefault')}
                title={t('conversionProfiles.markDefault')}
              >
                <Star size={14} />
              </button>
            )}
            {!selectedPreset.is_builtin && (
              <button
                type="button"
                className="settings-modal__option settings-modal__option--icon"
                onClick={() => handleDeletePreset(selectedPreset)}
                aria-label={t('conversionProfiles.delete')}
                title={t('conversionProfiles.delete')}
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        )}
      </div>

      <div className="preview-settings__quick-slots">
        <h4 className="settings-modal__section-title">{t('previewSettings.quickSlots')}</h4>
        <div className="settings-modal__actions">
          {quickSlots.map((slot, index) => (
            <div key={QUICK_SLOT_NAMES[index]} className="preview-settings__quick-slot">
              <button type="button" className="settings-modal__option" onClick={() => void handleSaveToSlot(index)}>
                <Save size={14} /> {t('previewSettings.saveToSlot', { slot: index + 1 })}
              </button>
              {slot && (
                <button type="button" className="settings-modal__option" onClick={() => loadPreset(slot)}>
                  <FolderOpen size={14} /> {t('previewSettings.loadSlot', { slot: index + 1 })}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <label className="settings-modal__label">
        {t('previewSettings.presetName')}
        <input
          className="settings-modal__input"
          value={presetName}
          onChange={(event) => setPresetName(event.target.value)}
        />
      </label>

      {saveError && <p className="settings-modal__hint settings-modal__hint--error">{saveError}</p>}

      <div className="settings-modal__actions">
        <button
          type="button"
          className="settings-modal__option"
          onClick={() => void handleSavePreset(false)}
          disabled={saving || !presetName || Boolean(layoutError)}
        >
          <Save size={14} /> {t('previewSettings.savePreset')}
        </button>
        <button
          type="button"
          className="settings-modal__option"
          onClick={() => void handleSavePreset(true)}
          disabled={saving || !presetName || Boolean(layoutError)}
        >
          <Copy size={14} /> {t('previewSettings.saveAsNewPreset')}
        </button>
      </div>
      </>
      )}
    </section>
  )
}
