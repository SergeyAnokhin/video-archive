import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronLeft, ChevronRight, Copy, Info, Link, PlayCircle, X } from 'lucide-react'
import type { FileEntry, PlaybackInfo, PlaybackMode } from '../types/api'
import { FolderQuickActions } from './FolderQuickActions'
import { QuickTagAdd } from './QuickTagAdd'
import './PlaybackModal.css'

interface PlaybackModalProps {
  file: FileEntry
  onClose: () => void
  onMoved?: () => void
  onOpenInfo?: () => void
  onTagAdded?: () => void
  hasPrev?: boolean
  hasNext?: boolean
  onPrev?: () => void
  onNext?: () => void
}

export function PlaybackModal({
  file,
  onClose,
  onMoved,
  onOpenInfo,
  onTagAdded,
  hasPrev,
  hasNext,
  onPrev,
  onNext,
}: PlaybackModalProps) {
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
      } else if (event.key === 'ArrowLeft' && hasPrev && onPrev) {
        onPrev()
      } else if (event.key === 'ArrowRight' && hasNext && onNext) {
        onNext()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose, hasPrev, hasNext, onPrev, onNext])

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
      <div className="playback-overlay__top-left" onClick={(event) => event.stopPropagation()}>
        {onMoved && <FolderQuickActions fileId={file.id} onMoved={onMoved} />}
        <div className="playback-overlay__quick-actions">
          {onOpenInfo && (
            <button
              type="button"
              className="playback-overlay__info-toggle"
              aria-label={t('playbackModal.info')}
              title={t('playbackModal.info')}
              onClick={onOpenInfo}
            >
              <Info size={16} />
            </button>
          )}
          <QuickTagAdd fileId={file.id} onTagAdded={onTagAdded} />
        </div>
      </div>

      <div className="playback-overlay__top-right" onClick={(event) => event.stopPropagation()}>
        {info && (
          <button
            type="button"
            className="playback-overlay__mode-toggle"
            onClick={() => setMode(mode === 'stream' ? 'direct_link' : 'stream')}
          >
            {mode === 'stream' ? <Link size={14} /> : <PlayCircle size={14} />}{' '}
            {mode === 'stream' ? t('playbackModal.switchToDirectLink') : t('playbackModal.switchToStream')}
          </button>
        )}
        <button
          type="button"
          className="playback-overlay__close"
          aria-label={t('playbackModal.close')}
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>

      {hasPrev && onPrev && (
        <div
          className="playback-overlay__nav-zone playback-overlay__nav-zone--prev"
          role="button"
          tabIndex={0}
          aria-label={t('playbackModal.previous')}
          title={t('playbackModal.previous')}
          onClick={(event) => {
            event.stopPropagation()
            onPrev()
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              onPrev()
            }
          }}
        >
          <span className="playback-overlay__nav" aria-hidden="true">
            <ChevronLeft size={24} />
          </span>
        </div>
      )}

      {hasNext && onNext && (
        <div
          className="playback-overlay__nav-zone playback-overlay__nav-zone--next"
          role="button"
          tabIndex={0}
          aria-label={t('playbackModal.next')}
          title={t('playbackModal.next')}
          onClick={(event) => {
            event.stopPropagation()
            onNext()
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              onNext()
            }
          }}
        >
          <span className="playback-overlay__nav" aria-hidden="true">
            <ChevronRight size={24} />
          </span>
        </div>
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
            {copied ? <Check size={14} /> : <Copy size={14} />} {t('playbackModal.copyPath')}
          </button>
          {copied && <span className="playback-overlay__message">{t('playbackModal.copied')}</span>}
        </div>
      )}
    </div>
  )
}
