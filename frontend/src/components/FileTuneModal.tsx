import { Play, Save, SlidersHorizontal, Trash2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useConversionProfiles } from '../context/ConversionProfilesContext'
import type { FileEntry, JobItem, VariantOverride } from '../types/api'
import './ConvertDialog.css'

interface FileTuneModalProps {
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
function newRow(patch: Partial<VariantRow> = {}): VariantRow {
  rowCounter += 1
  return { key: `row-${rowCounter}`, maxDimension: '', crf: '', codec: '', ...patch }
}

function rowToOverride(row: VariantRow): VariantOverride {
  const override: VariantOverride = {}
  if (row.maxDimension) override.max_dimension = Number(row.maxDimension)
  if (row.crf) override.crf = Number(row.crf)
  if (row.codec) override.video_codec = row.codec
  return override
}

const CODEC_OPTIONS = ['h265', 'h264', 'vp9', 'av1']

type SweepParameter = 'dimension' | 'crf' | 'codec'

// Centered on the app's own defaults (h265 CRF 26, Specification §7): a
// narrow band around "good enough to archive" so the sweep still finishes
// quickly and every generated variant is a plausible real choice, not a
// throwaway extreme.
const DEFAULT_SWEEP_RANGES: Record<'dimension' | 'crf', { min: number; max: number; step: number }> = {
  crf: { min: 22, max: 30, step: 4 },
  dimension: { min: 960, max: 1920, step: 480 },
}

function generateRange(min: number, max: number, step: number): number[] {
  const values: number[] = []
  for (let value = min; value <= max; value += step) {
    values.push(value)
  }
  return values
}

export function FileTuneModal({ file, onClose, onStarted }: FileTuneModalProps) {
  const { t } = useTranslation()
  const { profiles, loading, refresh: refreshProfiles, ensureDefaultProfile } = useConversionProfiles()
  const [profileId, setProfileId] = useState(profiles.find((p) => p.is_default)?.id ?? profiles[0]?.id ?? '')
  const [rows, setRows] = useState<VariantRow[]>([])
  const [sweepParameter, setSweepParameter] = useState<SweepParameter>('crf')
  const [sweepMin, setSweepMin] = useState(String(DEFAULT_SWEEP_RANGES.crf.min))
  const [sweepMax, setSweepMax] = useState(String(DEFAULT_SWEEP_RANGES.crf.max))
  const [sweepStep, setSweepStep] = useState(String(DEFAULT_SWEEP_RANGES.crf.step))
  const [sweepCodecs, setSweepCodecs] = useState<string[]>([])
  const [generateError, setGenerateError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sweepJobId, setSweepJobId] = useState<string | null>(null)
  const [submittedOverrides, setSubmittedOverrides] = useState<VariantOverride[]>([])
  const [items, setItems] = useState<JobItem[]>([])
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    if (profileId || loading) {
      return
    }
    if (profiles.length > 0) {
      setProfileId(profiles.find((p) => p.is_default)?.id ?? profiles[0].id)
      return
    }
    void ensureDefaultProfile(t('conversionProfiles.default')).then((profile) => setProfileId(profile.id))
  }, [profiles, loading, profileId, ensureDefaultProfile, t])

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

  async function handleStart() {
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

  function removeRow(key: string) {
    setRows((current) => current.filter((row) => row.key !== key))
  }

  function toggleSweepCodec(codec: string) {
    setSweepCodecs((current) =>
      current.includes(codec) ? current.filter((c) => c !== codec) : [...current, codec],
    )
  }

  function handleGenerate() {
    setGenerateError(null)

    if (sweepParameter === 'codec') {
      if (sweepCodecs.length === 0) {
        setGenerateError(t('convertDialog.variantsGenerateErrorCodec'))
        return
      }
      setRows(sweepCodecs.map((codec) => newRow({ codec })))
      return
    }

    const min = Number(sweepMin)
    const max = Number(sweepMax)
    const step = Number(sweepStep)
    if (!sweepMin || !sweepMax || !sweepStep || Number.isNaN(min) || Number.isNaN(max) || Number.isNaN(step) || min > max || step <= 0) {
      setGenerateError(t('convertDialog.variantsGenerateError'))
      return
    }

    const values = generateRange(min, max, step)
    setRows(
      values.map((value) =>
        sweepParameter === 'dimension' ? newRow({ maxDimension: String(value) }) : newRow({ crf: String(value) }),
      ),
    )
  }

  const baseProfile = profiles.find((p) => p.id === profileId)

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('convertDialog.tuneFileTitle')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">
          <SlidersHorizontal size={18} /> {t('convertDialog.tuneFileTitle')}
        </h2>
        <p className="convert-dialog__hint">{file.file_name}</p>

        <div className="convert-dialog__panel">
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

          {!sweepJobId && (
            <>
              <p className="convert-dialog__hint">{t('convertDialog.variantsHint')}</p>

              <label className="convert-dialog__label">
                {t('convertDialog.variantsParameter')}
                <select
                  className="convert-dialog__input"
                  value={sweepParameter}
                  onChange={(event) => {
                    const next = event.target.value as SweepParameter
                    setSweepParameter(next)
                    if (next !== 'codec') {
                      const defaults = DEFAULT_SWEEP_RANGES[next]
                      setSweepMin(String(defaults.min))
                      setSweepMax(String(defaults.max))
                      setSweepStep(String(defaults.step))
                    }
                  }}
                >
                  <option value="dimension">{t('convertDialog.variantsParameterDimension')}</option>
                  <option value="crf">{t('convertDialog.variantsParameterCrf')}</option>
                  <option value="codec">{t('convertDialog.variantsParameterCodec')}</option>
                </select>
              </label>

              {sweepParameter === 'codec' ? (
                <div className="convert-dialog__codec-options">
                  {CODEC_OPTIONS.map((codec) => (
                    <label key={codec} className="convert-dialog__checkbox">
                      <input
                        type="checkbox"
                        checked={sweepCodecs.includes(codec)}
                        onChange={() => toggleSweepCodec(codec)}
                      />
                      {codec.toUpperCase()}
                    </label>
                  ))}
                </div>
              ) : (
                <div className="convert-dialog__sweep-range">
                  <input
                    type="number"
                    placeholder={t('convertDialog.variantsMin')}
                    value={sweepMin}
                    onChange={(event) => setSweepMin(event.target.value)}
                  />
                  <input
                    type="number"
                    placeholder={t('convertDialog.variantsMax')}
                    value={sweepMax}
                    onChange={(event) => setSweepMax(event.target.value)}
                  />
                  <input
                    type="number"
                    placeholder={t('convertDialog.variantsStep')}
                    value={sweepStep}
                    onChange={(event) => setSweepStep(event.target.value)}
                  />
                </div>
              )}

              {generateError && (
                <p className="convert-dialog__hint convert-dialog__hint--error">{generateError}</p>
              )}

              <div className="convert-dialog__actions">
                <button type="button" className="convert-dialog__button" onClick={handleGenerate}>
                  <SlidersHorizontal size={14} /> {t('convertDialog.variantsGenerate')}
                </button>
              </div>

              {rows.length > 0 && (
                <>
                  <p className="convert-dialog__hint">{t('convertDialog.variantsGenerated')}</p>
                  {rows.map((row) => (
                    <div key={row.key} className="convert-dialog__variant-row">
                      <span>
                        {row.maxDimension && `${t('convertDialog.variantMaxDimension')}: ${row.maxDimension}`}
                        {row.crf && `${t('convertDialog.variantCrf')}: ${row.crf}`}
                        {row.codec && row.codec.toUpperCase()}
                      </span>
                      <button
                        type="button"
                        className="convert-dialog__button convert-dialog__button--icon"
                        onClick={() => removeRow(row.key)}
                        aria-label={t('convertDialog.variantsRemove')}
                        title={t('convertDialog.variantsRemove')}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </>
              )}

              {error && <p className="convert-dialog__hint convert-dialog__hint--error">{error}</p>}

              <div className="convert-dialog__actions">
                <button
                  type="button"
                  className="convert-dialog__button convert-dialog__button--primary"
                  onClick={handleStart}
                  disabled={starting || !profileId || rows.length === 0}
                >
                  <Play size={14} /> {t('convertDialog.start')}
                </button>
                <button type="button" className="convert-dialog__button" onClick={onClose}>
                  <X size={14} /> {t('convertDialog.cancel')}
                </button>
              </div>
            </>
          )}

          {sweepJobId && baseProfile && (
            <div className="convert-dialog__results">
              <p className="convert-dialog__hint">{t('convertDialog.resultsHint')}</p>
              {items.length === 0 && <p className="convert-dialog__hint">{t('convertDialog.resultsWaiting')}</p>}
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
                  <X size={14} /> {t('convertDialog.close')}
                </button>
              </div>
            </div>
          )}
        </div>
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
          <Save size={14} /> {t('convertDialog.saveAsProfile')}
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
            <Save size={14} /> {t('conversionProfiles.save')}
          </button>
        </>
      )}
    </div>
  )
}
