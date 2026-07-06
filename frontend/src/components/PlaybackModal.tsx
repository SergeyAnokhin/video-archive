import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import type { FileEntry, PlaybackInfo, PlaybackMode } from '../types/api'
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

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  async function handleCopyPath() {
    if (!info) {
      return
    }
    await navigator.clipboard.writeText(info.direct_path)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="playback-overlay" role="dialog" aria-modal="true" aria-label={file.file_name} onClick={onClose}>
      <button
        type="button"
        className="playback-overlay__close"
        aria-label={t('playbackModal.close')}
        onClick={(event) => {
          event.stopPropagation()
          onClose()
        }}
      >
        <X size={20} />
      </button>

      {info && (
        <button
          type="button"
          className="playback-overlay__mode-toggle"
          onClick={(event) => {
            event.stopPropagation()
            setMode(mode === 'stream' ? 'direct_link' : 'stream')
          }}
        >
          {mode === 'stream' ? t('playbackModal.switchToDirectLink') : t('playbackModal.switchToStream')}
        </button>
      )}

      {error && (
        <p className="playback-overlay__message playback-overlay__message--error">
          {t('playbackModal.loadError', { message: error })}
        </p>
      )}
      {!error && !info && <p className="playback-overlay__message">{t('playbackModal.loading')}</p>}

      {info && mode === 'stream' && (
        <video
          className="playback-overlay__video"
          controls
          autoPlay
          onClick={(event) => event.stopPropagation()}
        >
          <source src={info.stream_url} />
          {t('playbackModal.streamNotSupported')}
        </video>
      )}

      {info && mode === 'direct_link' && (
        <div className="playback-overlay__direct-link" onClick={(event) => event.stopPropagation()}>
          <p className="playback-overlay__message">{t('playbackModal.directLinkHint')}</p>
          <code className="playback-overlay__path">{info.direct_path}</code>
          <button type="button" className="playback-overlay__copy-btn" onClick={() => void handleCopyPath()}>
            {t('playbackModal.copyPath')}
          </button>
          {copied && <span className="playback-overlay__message">{t('playbackModal.copied')}</span>}
        </div>
      )}
    </div>
  )
}
