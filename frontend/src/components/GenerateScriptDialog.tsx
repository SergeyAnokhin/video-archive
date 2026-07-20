import { Check, Copy, Download, Play, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useConversionProfiles } from '../context/ConversionProfilesContext'
import { api } from '../api/client'
import './ConvertDialog.css'

interface GenerateScriptDialogProps {
  path: string
  onClose: () => void
}

interface GenerateScriptResponse {
  script: string
  file_count: number
  container: string
}

const PRESETS = [
  'ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow',
] as const

export function GenerateScriptDialog({ path, onClose }: GenerateScriptDialogProps) {
  const { t } = useTranslation()
  const { profiles } = useConversionProfiles()
  const [profileId, setProfileId] = useState(profiles.find((p) => p.is_default)?.id ?? profiles[0]?.id ?? '')
  const selectedProfile = profiles.find((p) => p.id === profileId) ?? null

  const [videoCodec, setVideoCodec] = useState('h265')
  const [crf, setCrf] = useState('26')
  const [maxDimension, setMaxDimension] = useState('')
  const [dropAudio, setDropAudio] = useState(true)
  const [hardwareAccel, setHardwareAccel] = useState('off')
  const [preset, setPreset] = useState('medium')
  const [extraArgsText, setExtraArgsText] = useState('')

  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<GenerateScriptResponse | null>(null)
  const [copied, setCopied] = useState(false)

  // Reset the override fields to the picked profile's own values whenever
  // the profile selection changes, so the form starts from something
  // meaningful instead of an unrelated previous profile's leftover values.
  useEffect(() => {
    if (!selectedProfile) return
    setVideoCodec(selectedProfile.video_codec)
    setCrf(String(selectedProfile.crf))
    setMaxDimension(selectedProfile.max_dimension ? String(selectedProfile.max_dimension) : '')
    setDropAudio(selectedProfile.drop_audio)
    setHardwareAccel(selectedProfile.hardware_accel)
    setPreset(selectedProfile.preset)
  }, [profileId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate() {
    setGenerating(true)
    setError(null)
    try {
      const extraArgs = extraArgsText.trim() ? extraArgsText.trim().split(/\s+/) : []
      const data = await api<GenerateScriptResponse>('/api/jobs/generate-conversion-script', {
        method: 'POST',
        body: {
          path,
          profile_id: profileId,
          overrides: {
            video_codec: videoCodec,
            crf: Number(crf),
            max_dimension: maxDimension ? Number(maxDimension) : null,
            drop_audio: dropAudio,
            hardware_accel: hardwareAccel,
            preset,
            extra_encoder_args: extraArgs,
          },
        },
      })
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setGenerating(false)
    }
  }

  async function handleCopy() {
    if (!result) return
    await navigator.clipboard.writeText(result.script)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleDownload() {
    if (!result) return
    const blob = new Blob([result.script], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const folderName = path ? path.split('/').pop() : 'root'
    const link = document.createElement('a')
    link.href = url
    link.download = `convert-${folderName || 'root'}.ps1`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog convert-dialog--wide"
        role="dialog"
        aria-modal="true"
        aria-label={t('generateScriptDialog.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{t('generateScriptDialog.title')}</h2>
        <p className="convert-dialog__hint">
          {t('convertDialog.scopePath', { path: path || t('library.root') })}
        </p>

        {!result ? (
          profiles.length === 0 ? (
            <p className="convert-dialog__hint convert-dialog__hint--warning">
              {t('convertDialog.noProfiles')}
            </p>
          ) : (
            <>
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

              <label className="convert-dialog__label">
                {t('conversionProfiles.codec')}
                <select
                  className="convert-dialog__input"
                  value={videoCodec}
                  onChange={(event) => setVideoCodec(event.target.value)}
                >
                  <option value="h265">H.265</option>
                  <option value="h264">H.264</option>
                  <option value="vp9">VP9</option>
                  <option value="av1">AV1</option>
                </select>
              </label>

              <label className="convert-dialog__label">
                {t('conversionProfiles.hardwareAccel')}
                <select
                  className="convert-dialog__input"
                  value={hardwareAccel}
                  onChange={(event) => setHardwareAccel(event.target.value)}
                >
                  <option value="off">{t('conversionProfiles.hardwareAccelOff')}</option>
                  <option value="qsv">{t('conversionProfiles.hardwareAccelQsv')}</option>
                  <option value="vaapi">{t('conversionProfiles.hardwareAccelVaapi')}</option>
                </select>
              </label>

              <label className="convert-dialog__label">
                {t('conversionProfiles.preset')}
                <select
                  className="convert-dialog__input"
                  value={preset}
                  onChange={(event) => setPreset(event.target.value)}
                >
                  {PRESETS.map((value) => (
                    <option key={value} value={value}>
                      {t(`conversionProfiles.preset${value.charAt(0).toUpperCase()}${value.slice(1)}`)}
                    </option>
                  ))}
                </select>
                <span className="convert-dialog__hint">{t('conversionProfiles.presetHint')}</span>
              </label>

              <div className="convert-dialog__codec-options">
                <label className="convert-dialog__label">
                  {t('conversionProfiles.maxDimension')}
                  <input
                    className="convert-dialog__input"
                    type="number"
                    min={1}
                    value={maxDimension}
                    onChange={(event) => setMaxDimension(event.target.value)}
                    placeholder={t('conversionProfiles.noResize')}
                  />
                </label>
                <label className="convert-dialog__label">
                  {t('conversionProfiles.crf')}
                  <input
                    className="convert-dialog__input"
                    type="number"
                    min={0}
                    max={51}
                    value={crf}
                    onChange={(event) => setCrf(event.target.value)}
                  />
                </label>
              </div>

              <label className="convert-dialog__checkbox">
                <input
                  type="checkbox"
                  checked={dropAudio}
                  onChange={(event) => setDropAudio(event.target.checked)}
                />
                {t('conversionProfiles.dropAudio')}
              </label>

              <label className="convert-dialog__label">
                {t('generateScriptDialog.extraArgs')}
                <input
                  className="convert-dialog__input"
                  value={extraArgsText}
                  onChange={(event) => setExtraArgsText(event.target.value)}
                  placeholder={t('generateScriptDialog.extraArgsPlaceholder')}
                />
              </label>
            </>
          )
        ) : (
          <>
            <p className="convert-dialog__hint">
              {t('generateScriptDialog.fileCount', { count: result.file_count })}
            </p>
            <textarea
              className="convert-dialog__input generate-script-dialog__output"
              readOnly
              value={result.script}
              rows={16}
              onFocus={(event) => event.target.select()}
            />
          </>
        )}

        {error && <p className="convert-dialog__hint convert-dialog__hint--error">{error}</p>}

        <div className="convert-dialog__actions">
          {!result ? (
            <button
              type="button"
              className="convert-dialog__button convert-dialog__button--primary"
              onClick={handleGenerate}
              disabled={generating || !profileId}
            >
              <Play size={14} /> {t('generateScriptDialog.generate')}
            </button>
          ) : (
            <>
              <button type="button" className="convert-dialog__button convert-dialog__button--primary" onClick={handleCopy}>
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? t('generateScriptDialog.copied') : t('generateScriptDialog.copy')}
              </button>
              <button type="button" className="convert-dialog__button" onClick={handleDownload}>
                <Download size={14} /> {t('generateScriptDialog.download')}
              </button>
            </>
          )}
          <button type="button" className="convert-dialog__button" onClick={onClose}>
            <X size={14} /> {t('convertDialog.cancel')}
          </button>
        </div>
      </div>
    </div>
  )
}
