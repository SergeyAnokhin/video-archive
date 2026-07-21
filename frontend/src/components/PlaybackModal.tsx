import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronLeft, ChevronRight, Copy, ExternalLink, Info, Link, PlayCircle, Trash2, X } from 'lucide-react'
import { api } from '../api/client'
import type { FileEntry, PlaybackInfo, PlaybackMode } from '../types/api'
import { FolderQuickActions } from './FolderQuickActions'
import { QuickTagAdd } from './QuickTagAdd'
import { UserDefinedTagButton } from './UserDefinedTagButton'
import './PlaybackModal.css'

interface PlaybackModalProps {
  file: FileEntry
  onClose: () => void
  onMoved?: () => void
  onOpenInfo?: () => void
  onDelete?: () => void
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
  onDelete,
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
  // Which of the two tag-add popovers is open, if any (user report: opening
  // one while the other was already open left both stacked on screen).
  const [openTagPicker, setOpenTagPicker] = useState<'quick' | 'user' | null>(null)

  useEffect(() => {
    let cancelled = false
    // Reset before fetching the new file's info (user report: prev/next
    // looked like it did nothing at all -- see the <video key={file.id}>
    // comment below for why leaving the previous file's `info` on screen
    // during this fetch is what actually broke it, not just a loading flash).
    setInfo(null)
    setMode(null)
    setError(null)
    void (async () => {
      try {
        const json = await api<PlaybackInfo>(`/api/files/${file.id}/playback`)
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
    // Capture phase (user report: arrow keys did nothing once the focused
    // native <video controls> element had already consumed ArrowLeft/Right
    // itself, for its own seek-by-a-few-seconds shortcut, before the event
    // reached a bubble-phase listener here) -- this way the app's own
    // prev/next always sees the key first, regardless of what the video
    // element does with it afterward.
    document.addEventListener('keydown', handleKeyDown, true)
    return () => document.removeEventListener('keydown', handleKeyDown, true)
  }, [onClose, hasPrev, hasNext, onPrev, onNext])

  async function handleCopyPath() {
    if (!info) {
      return
    }
    await navigator.clipboard.writeText(info.direct_path)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleDelete() {
    if (onDelete && window.confirm(t('library.confirmDeleteFile', { name: file.file_name }))) {
      onDelete()
    }
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
          <QuickTagAdd
            fileId={file.id}
            onTagAdded={onTagAdded}
            open={openTagPicker === 'quick'}
            onOpenChange={(open) => setOpenTagPicker(open ? 'quick' : null)}
          />
          <UserDefinedTagButton
            fileId={file.id}
            onTagAdded={onTagAdded}
            open={openTagPicker === 'user'}
            onOpenChange={(open) => setOpenTagPicker(open ? 'user' : null)}
          />
        </div>
      </div>

      <div className="playback-overlay__top-right" onClick={(event) => event.stopPropagation()}>
        {info && (
          <button
            type="button"
            className="playback-overlay__mode-toggle"
            aria-label={mode === 'stream' ? t('playbackModal.switchToDirectLink') : t('playbackModal.switchToStream')}
            title={mode === 'stream' ? t('playbackModal.switchToDirectLink') : t('playbackModal.switchToStream')}
            onClick={() => setMode(mode === 'stream' ? 'direct_link' : 'stream')}
          >
            {mode === 'stream' ? <Link size={14} /> : <PlayCircle size={14} />}
            <span className="playback-overlay__mode-toggle-label">
              {mode === 'stream' ? t('playbackModal.switchToDirectLink') : t('playbackModal.switchToStream')}
            </span>
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            className="playback-overlay__delete"
            aria-label={t('library.deleteFile')}
            title={t('library.deleteFile')}
            onClick={handleDelete}
          >
            <Trash2 size={16} />
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
          // Keyed by file id (user report: prev/next updated every bit of
          // app state -- the dialog's file, the nav buttons -- but the
          // actual playing video never changed). A <video><source src=.../>
          // element does NOT reload just because its <source> child's `src`
          // attribute changes on a re-render -- the browser only reads
          // <source> children once, when the element is first attached.
          // Without a `key` tied to the file, switching files left the
          // *original* video playing forever under the hood while
          // everything else silently moved on. The `key` forces React to
          // unmount/remount a fresh <video> per file, which does load its
          // <source> normally, same as a first-ever mount.
          key={file.id}
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

          <p className="playback-overlay__message">{t('playbackModal.rawStreamHint')}</p>
          <a
            className="playback-overlay__copy-btn"
            href={info.stream_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            <ExternalLink size={14} /> {t('playbackModal.openRawStream')}
          </a>
        </div>
      )}
    </div>
  )
}
