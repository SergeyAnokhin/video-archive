import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { FileEntry, PlaybackInfo, PlaybackMode } from '../types/api'
import './ConvertDialog.css'
import './PlaybackModal.css'

interface PlaybackModalProps {
  file: FileEntry
  onClose: () => void
}

export function PlaybackModal({ file, onClose }: PlaybackModalProps) {
  const { t } = useTranslation()
  const [info, setInfo] = useState<PlaybackInfo | null>(null)
  const [mode, setMode] = useState<PlaybackMode | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await fetch(`/api/files/${file.id}/playback`)
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`)
        }
        const json: PlaybackInfo = await res.json()
        if (!cancelled) {
          setInfo(json)
          setMode(json.mode)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [file.id])

  async function handleCopyPath() {
    if (!info) {
      return
    }
    await navigator.clipboard.writeText(info.direct_path)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog playback-modal"
        role="dialog"
        aria-modal="true"
        aria-label={t('playbackModal.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">{file.file_name}</h2>

        {error && (
          <p className="convert-dialog__hint convert-dialog__hint--error">
            {t('playbackModal.loadError', { message: error })}
          </p>
        )}
        {!error && !info && <p className="convert-dialog__hint">{t('playbackModal.loading')}</p>}

        {info && mode === 'stream' && (
          <video className="playback-modal__video" controls autoPlay>
            <source src={info.stream_url} />
            {t('playbackModal.streamNotSupported')}
          </video>
        )}

        {info && mode === 'direct_link' && (
          <div className="playback-modal__direct-link">
            <p className="convert-dialog__hint">{t('playbackModal.directLinkHint')}</p>
            <code className="playback-modal__path">{info.direct_path}</code>
            <div className="convert-dialog__actions">
              <button type="button" className="convert-dialog__button" onClick={() => void handleCopyPath()}>
                {t('playbackModal.copyPath')}
              </button>
              {copied && <span className="convert-dialog__hint">{t('playbackModal.copied')}</span>}
            </div>
          </div>
        )}

        {info && (
          <div className="convert-dialog__actions">
            <button
              type="button"
              className="convert-dialog__button"
              onClick={() => setMode(mode === 'stream' ? 'direct_link' : 'stream')}
            >
              {mode === 'stream' ? t('playbackModal.switchToDirectLink') : t('playbackModal.switchToStream')}
            </button>
            <button type="button" className="convert-dialog__button" onClick={onClose}>
              {t('playbackModal.close')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
