import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useConversionProfiles } from '../context/ConversionProfilesContext'
import type { ConversionMode, FileEntry, JobItem, VariantOverride } from '../types/api'
import './ConvertDialog.css'

interface FileConvertModalProps {
  file: FileEntry
  onClose: () => void
  onStarted: () => void
}

interface VariantRow {
  key: string
  maxDimension: string
  crf: string
  codec: string
}

let rowCounter = 0
function newRow(): VariantRow {
  rowCounter += 1
  return { key: `row-${rowCounter}`, maxDimension: '', crf: '', codec: '' }
}

function rowToOverride(row: VariantRow): VariantOverride {
  const override: VariantOverride = {}
  if (row.maxDimension) override.max_dimension = Number(row.maxDimension)
  if (row.crf) override.crf = Number(row.crf)
  if (row.codec) override.video_codec = row.codec
  return override
}

export function FileConvertModal({ file, onClose, onStarted }: FileConvertModalProps) {
  const { t } = useTranslation()
  const { profiles, refresh: refreshProfiles } = useConversionProfiles()
  const [tab, setTab] = useState<'convert' | 'variants'>('convert')
  const [profileId, setProfileId] = useState(profiles.find((p) => p.is_default)?.id ?? profiles[0]?.id ?? '')
  const [mode, setMode] = useState<ConversionMode>('production')
  const [skipProcessed, setSkipProcessed] = useState(true)
  const [rows, setRows] = useState<VariantRow[]>([newRow(), newRow()])
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sweepJobId, setSweepJobId] = useState<string | null>(null)
  const [submittedOverrides, setSubmittedOverrides] = useState<VariantOverride[]>([])
  const [items, setItems] = useState<JobItem[]>([])
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    if (!sweepJobId) {
      return
    }
    async function poll() {
      const res = await fetch(`/api/jobs/${sweepJobId}/items`)
      if (res.ok) {
        const data: { items: JobItem[] } = await res.json()
        setItems(data.items)
      }
    }
    void poll()
    pollRef.current = window.setInterval(() => void poll(), 1500)
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
      }
    }
  }, [sweepJobId])

  async function handleStartConvert() {
    setStarting(true)
    setError(null)
    try {
      const res = await fetch('/api/jobs/convert-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: file.id,
          profile_id: profileId,
          mode,
          skip_processed: skipProcessed,
        }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      onStarted()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setStarting(false)
    }
  }

  async function handleStartVariants() {
    setStarting(true)
    setError(null)
    try {
      const overrides = rows.map(rowToOverride)
      const res = await fetch('/api/jobs/convert-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: file.id,
          profile_id: profileId,
          mode: 'test',
          variants: overrides,
        }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      const job = await res.json()
      onStarted()
      setSubmittedOverrides(overrides)
      setSweepJobId(job.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setStarting(false)
    }
  }

  function updateRow(key: string, patch: Partial<VariantRow>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  const baseProfile = profiles.find((p) => p.id === profileId)

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('convertDialog.fileTitle')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('convertDialog.fileTitle')}</h2>
        <p className="convert-dialog__hint">{file.file_name}</p>

        {profiles.length === 0 ? (
          <p className="convert-dialog__hint convert-dialog__hint--warning">
            {t('convertDialog.noProfiles')}
          </p>
        ) : (
          <>
            <div className="convert-dialog__tabs" role="tablist">
              <button
                type="button"
                className="convert-dialog__tab"
                role="tab"
                aria-selected={tab === 'convert'}
                onClick={() => setTab('convert')}
              >
                {t('convertDialog.convertTab')}
              </button>
              <button
                type="button"
                className="convert-dialog__tab"
                role="tab"
                aria-selected={tab === 'variants'}
                onClick={() => setTab('variants')}
              >
                {t('convertDialog.variantsTab')}
              </button>
            </div>

            <label className="convert-dialog__label">
              {t('convertDialog.profile')}
              <select
                className="convert-dialog__input"
                value={profileId}
                onChange={(event) => setProfileId(event.target.value)}
              >
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
            </label>

            {tab === 'convert' && !sweepJobId && (
              <>
                <fieldset className="convert-dialog__fieldset">
                  <legend>{t('convertDialog.mode')}</legend>
                  <label className="convert-dialog__radio">
                    <input
                      type="radio"
                      checked={mode === 'production'}
                      onChange={() => setMode('production')}
                    />
                    {t('convertDialog.modeProduction')}
                  </label>
                  <label className="convert-dialog__radio">
                    <input type="radio" checked={mode === 'test'} onChange={() => setMode('test')} />
                    {t('convertDialog.modeTest')}
                  </label>
                </fieldset>

                <label className="convert-dialog__checkbox">
                  <input
                    type="checkbox"
                    checked={skipProcessed}
                    onChange={(event) => setSkipProcessed(event.target.checked)}
                  />
                  {t('convertDialog.skipProcessed')}
                </label>

                {error && <p className="convert-dialog__hint convert-dialog__hint--error">{error}</p>}

                <div className="convert-dialog__actions">
                  <button
                    type="button"
                    className="convert-dialog__button convert-dialog__button--primary"
                    onClick={handleStartConvert}
                    disabled={starting || !profileId}
                  >
                    {t('convertDialog.start')}
                  </button>
                  <button type="button" className="convert-dialog__button" onClick={onClose}>
                    {t('convertDialog.cancel')}
                  </button>
                </div>
              </>
            )}

            {tab === 'variants' && (
              <>
                {!sweepJobId && (
                  <>
                    <p className="convert-dialog__hint">{t('convertDialog.variantsHint')}</p>
                    {rows.map((row) => (
                      <div key={row.key} className="convert-dialog__variant-row">
                        <input
                          type="number"
                          placeholder={t('convertDialog.variantMaxDimension')}
                          value={row.maxDimension}
                          onChange={(event) => updateRow(row.key, { maxDimension: event.target.value })}
                        />
                        <input
                          type="number"
                          min={22}
                          max={32}
                          placeholder={t('convertDialog.variantCrf')}
                          value={row.crf}
                          onChange={(event) => updateRow(row.key, { crf: event.target.value })}
                        />
                        <select
                          value={row.codec}
                          onChange={(event) => updateRow(row.key, { codec: event.target.value })}
                        >
                          <option value="">{t('convertDialog.variantCodecInherit')}</option>
                          <option value="h265">H.265</option>
                          <option value="h264">H.264</option>
                          <option value="vp9">VP9</option>
                          <option value="av1">AV1</option>
                        </select>
                        <button
                          type="button"
                          className="convert-dialog__button"
                          onClick={() => setRows((current) => current.filter((r) => r.key !== row.key))}
                          disabled={rows.length <= 1}
                        >
                          {t('convertDialog.variantsRemove')}
                        </button>
                      </div>
                    ))}
                    <div className="convert-dialog__actions">
                      <button
                        type="button"
                        className="convert-dialog__button"
                        onClick={() => setRows((current) => [...current, newRow()])}
                      >
                        {t('convertDialog.variantsAdd')}
                      </button>
                    </div>

                    {error && <p className="convert-dialog__hint convert-dialog__hint--error">{error}</p>}

                    <div className="convert-dialog__actions">
                      <button
                        type="button"
                        className="convert-dialog__button convert-dialog__button--primary"
                        onClick={handleStartVariants}
                        disabled={starting || !profileId}
                      >
                        {t('convertDialog.start')}
                      </button>
                      <button type="button" className="convert-dialog__button" onClick={onClose}>
                        {t('convertDialog.cancel')}
                      </button>
                    </div>
                  </>
                )}

                {sweepJobId && baseProfile && (
                  <div className="convert-dialog__results">
                    <p className="convert-dialog__hint">{t('convertDialog.resultsHint')}</p>
                    {items.length === 0 && (
                      <p className="convert-dialog__hint">{t('convertDialog.resultsWaiting')}</p>
                    )}
                    {items.map((item, index) => (
                      <VariantResultRow
                        key={item.id}
                        item={item}
                        override={submittedOverrides[index] ?? {}}
                        baseProfile={baseProfile}
                        onPromoted={refreshProfiles}
                      />
                    ))}
                    <div className="convert-dialog__actions">
                      <button type="button" className="convert-dialog__button" onClick={onClose}>
                        {t('convertDialog.close')}
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

interface VariantResultRowProps {
  item: JobItem
  override: VariantOverride
  baseProfile: { video_codec: string; container: string; max_dimension: number | null; crf: number; drop_audio: boolean }
  onPromoted: () => Promise<void>
}

function VariantResultRow({ item, override, baseProfile, onPromoted }: VariantResultRowProps) {
  const { t } = useTranslation()
  const [promoting, setPromoting] = useState(false)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    setSaving(true)
    try {
      await fetch('/api/conversion-profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          video_codec: override.video_codec ?? baseProfile.video_codec,
          container: baseProfile.container,
          max_dimension: override.max_dimension ?? baseProfile.max_dimension,
          crf: override.crf ?? baseProfile.crf,
          drop_audio: baseProfile.drop_audio,
        }),
      })
      await onPromoted()
      setPromoting(false)
      setName('')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="convert-dialog__result-row">
      <span>{item.item_key ?? item.id}</span>
      <span className={`convert-dialog__result-status convert-dialog__result-status--${item.status}`}>
        {t(`jobs.itemStatus.${item.status}`, item.status)}
      </span>
      {item.status === 'completed' && !promoting && (
        <button type="button" className="convert-dialog__button" onClick={() => setPromoting(true)}>
          {t('convertDialog.saveAsProfile')}
        </button>
      )}
      {promoting && (
        <>
          <input
            className="convert-dialog__input"
            placeholder={t('convertDialog.saveAsProfileNamePlaceholder')}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button
            type="button"
            className="convert-dialog__button convert-dialog__button--primary"
            onClick={handleSave}
            disabled={saving || !name}
          >
            {t('conversionProfiles.save')}
          </button>
        </>
      )}
    </div>
  )
}
