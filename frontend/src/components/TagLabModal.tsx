import { Play, Plus, Tags, X } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { FileEntry, ProviderEntry, TagLabRunResult } from '../types/api'
import { useTags } from '../context/TagsContext'
import './ConvertDialog.css'
import './TagLabModal.css'

interface TagLabModalProps {
  file: FileEntry
  onClose: () => void
  onApplied: () => void
}

interface SelectedTag {
  tag_id: string | null
  display_name: string
  score: number
  source: 'model' | 'manual'
}

function normalizeName(name: string): string {
  return name.trim().toLowerCase()
}

export function TagLabModal({ file, onClose, onApplied }: TagLabModalProps) {
  const { t } = useTranslation()
  const { tags: vocabularyTags } = useTags()
  const [entries, setEntries] = useState<ProviderEntry[]>([])
  const [entriesLoaded, setEntriesLoaded] = useState(false)
  const [entryId, setEntryId] = useState('')
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [result, setResult] = useState<TagLabRunResult | null>(null)
  const [selectedTags, setSelectedTags] = useState<SelectedTag[]>([])
  const [tagInput, setTagInput] = useState('')
  const [applying, setApplying] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/settings/provider-entries')
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { entries: ProviderEntry[] } | null) => {
        if (cancelled) {
          return
        }
        const enabled = (data?.entries ?? []).filter((entry) => entry.enabled)
        setEntries(enabled)
        setEntryId((current) => current || enabled[0]?.id || '')
      })
      .finally(() => {
        if (!cancelled) {
          setEntriesLoaded(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleRun() {
    setRunning(true)
    setRunError(null)
    setResult(null)
    setSelectedTags([])
    try {
      const res = await fetch(`/api/files/${file.id}/tag-lab/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_entry_id: entryId }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      const data: TagLabRunResult = await res.json()
      setResult(data)
      setSelectedTags(
        data.tags
          .filter((tag) => tag.score > 0)
          .map((tag) => ({ tag_id: tag.tag_id, display_name: tag.display_name, score: tag.score, source: 'model' })),
      )
    } catch (err) {
      setRunError(err instanceof Error ? err.message : String(err))
    } finally {
      setRunning(false)
    }
  }

  function handleRemoveTag(displayName: string) {
    setSelectedTags((current) => current.filter((tag) => normalizeName(tag.display_name) !== normalizeName(displayName)))
  }

  function handleAddTag(event: FormEvent) {
    event.preventDefault()
    const displayName = tagInput.trim()
    if (!displayName) {
      return
    }
    setSelectedTags((current) => {
      if (current.some((tag) => normalizeName(tag.display_name) === normalizeName(displayName))) {
        return current
      }
      return [...current, { tag_id: null, display_name: displayName, score: 100, source: 'manual' }]
    })
    setTagInput('')
  }

  async function handleApply() {
    if (!result) {
      return
    }
    setApplying(true)
    setApplyError(null)
    try {
      const res = await fetch(`/api/files/${file.id}/tag-lab/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider_type: result.provider_type,
          model_name: result.model_name,
          tags: selectedTags.map((tag) =>
            tag.source === 'model' ? { tag_id: tag.tag_id, score: tag.score } : { display_name: tag.display_name },
          ),
        }),
      })
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        throw new Error(json?.detail?.error?.message ?? `HTTP ${res.status}`)
      }
      onApplied()
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : String(err))
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="convert-dialog-overlay" onClick={onClose}>
      <div
        className="convert-dialog convert-dialog--wide"
        role="dialog"
        aria-modal="true"
        aria-label={t('tagLab.title')}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="convert-dialog__title">
          <Tags size={18} /> {t('tagLab.title')}
        </h2>
        <p className="convert-dialog__hint">{file.file_name}</p>

        <label className="convert-dialog__label">
          {t('tagLab.modelLabel')}
          <select
            className="convert-dialog__input"
            value={entryId}
            onChange={(event) => setEntryId(event.target.value)}
            disabled={entries.length === 0}
          >
            {entries.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.display_name} ({entry.provider_type}/{entry.vision_model ?? '?'})
              </option>
            ))}
          </select>
        </label>
        {entriesLoaded && entries.length === 0 && (
          <p className="convert-dialog__hint convert-dialog__hint--warning">{t('tagLab.modelEmptyHint')}</p>
        )}

        <div className="convert-dialog__actions">
          <button
            type="button"
            className="convert-dialog__button convert-dialog__button--primary"
            onClick={() => void handleRun()}
            disabled={running || !entryId}
          >
            <Play size={14} /> {t('tagLab.run')}
          </button>
        </div>

        {running && <p className="convert-dialog__hint">{t('tagLab.running')}</p>}
        {runError && <p className="convert-dialog__hint convert-dialog__hint--error">{runError}</p>}

        {result && (
          <div className="convert-dialog__results">
            <p className="convert-dialog__hint">{t('tagLab.imagesTitle')}</p>
            <div className="tag-lab__images">
              {result.images.map((image, index) => (
                <img key={index} src={image.data_url} alt="" className="tag-lab__image" />
              ))}
            </div>

            <details className="tag-lab__details">
              <summary>{t('tagLab.promptTitle')}</summary>
              <pre className="tag-lab__pre">{result.prompt}</pre>
            </details>

            <p className="tag-lab__usage">
              {t('tagLab.tokensIn', { count: result.tokens_in ?? '—' })}
              {' · '}
              {t('tagLab.tokensOut', { count: result.tokens_out ?? '—' })}
              {' · '}
              {result.estimated_cost_usd != null
                ? t('tagLab.estimatedCost', { cost: result.estimated_cost_usd.toFixed(4) })
                : t('tagLab.costUnavailable')}
            </p>

            <details className="tag-lab__details">
              <summary>{t('tagLab.rawResponseTitle')}</summary>
              <pre className="tag-lab__pre">{result.raw_response ?? ''}</pre>
            </details>

            <h3 className="tag-lab__section-title">{t('tagLab.suggestedTagsTitle')}</h3>
            {selectedTags.length === 0 && <p className="file-info-panel__tags-empty">{t('tagLab.noTagsSuggested')}</p>}
            {selectedTags.length > 0 && (
              <ul className="file-info-panel__tags-list">
                {selectedTags.map((tag) => (
                  <li key={tag.display_name} className="file-info-panel__tags-row">
                    <span className="file-info-panel__tags-name">{tag.display_name}</span>
                    <span className="file-info-panel__tags-score">{tag.score}%</span>
                    <button
                      type="button"
                      className="file-info-panel__tags-remove"
                      aria-label={t('library.tagsRemove', { name: tag.display_name })}
                      title={t('library.tagsRemove', { name: tag.display_name })}
                      onClick={() => handleRemoveTag(tag.display_name)}
                    >
                      <X size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <form className="file-info-panel__tags-add" onSubmit={handleAddTag}>
              <input
                type="text"
                list="tag-lab-tag-options"
                className="file-info-panel__tags-input"
                placeholder={t('library.tagsAddPlaceholder')}
                value={tagInput}
                onChange={(event) => setTagInput(event.target.value)}
              />
              <datalist id="tag-lab-tag-options">
                {vocabularyTags
                  .filter((vocabularyTag) => vocabularyTag.is_active)
                  .map((vocabularyTag) => (
                    <option key={vocabularyTag.id} value={vocabularyTag.display_name} />
                  ))}
              </datalist>
              <button
                type="submit"
                className="file-info-panel__tags-add-btn"
                disabled={!tagInput.trim()}
                aria-label={t('library.tagsAddButton')}
                title={t('library.tagsAddButton')}
              >
                <Plus size={14} />
              </button>
            </form>

            {applyError && <p className="convert-dialog__hint convert-dialog__hint--error">{applyError}</p>}
          </div>
        )}

        <div className="convert-dialog__actions">
          {result && (
            <button
              type="button"
              className="convert-dialog__button convert-dialog__button--primary"
              onClick={() => void handleApply()}
              disabled={applying}
            >
              {applying ? t('tagLab.applying') : t('tagLab.apply')}
            </button>
          )}
          <button type="button" className="convert-dialog__button" onClick={onClose}>
            <X size={14} /> {t('convertDialog.cancel')}
          </button>
        </div>
      </div>
    </div>
  )
}
