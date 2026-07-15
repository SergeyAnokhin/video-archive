import { Pencil, Play, Plus, Tags, ThumbsDown, ThumbsUp, X } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type {
  FileEntry,
  ModelPricing,
  ModelStats,
  ProviderEntry,
  Tag,
  TagLabPreparedResult,
  TagLabRunResult,
} from '../types/api'
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

function statsKey(providerType: string, modelName: string | null): string {
  return `${providerType}:${modelName ?? ''}`
}

export function TagLabModal({ file, onClose, onApplied }: TagLabModalProps) {
  const { t } = useTranslation()
  const [tagOptions, setTagOptions] = useState<Tag[]>([])
  const [entries, setEntries] = useState<ProviderEntry[]>([])
  const [entriesLoaded, setEntriesLoaded] = useState(false)
  const [entryId, setEntryId] = useState('')
  const [prices, setPrices] = useState<ModelPricing[]>([])
  const [ratings, setRatings] = useState<ModelStats[]>([])
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [result, setResult] = useState<TagLabRunResult | null>(null)
  const [preparing, setPreparing] = useState<TagLabPreparedResult | null>(null)
  const [selectedTags, setSelectedTags] = useState<SelectedTag[]>([])
  const [tagVotes, setTagVotes] = useState<Record<string, 1 | -1>>({})
  const [tagInput, setTagInput] = useState('')
  const [applying, setApplying] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [zoomedImage, setZoomedImage] = useState<string | null>(null)
  const [editingPrice, setEditingPrice] = useState(false)
  const [priceDraft, setPriceDraft] = useState({ input: '', output: '' })
  const [savingPrice, setSavingPrice] = useState(false)

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

  useEffect(() => {
    fetch('/api/tags/used?limit=500')
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { tags: Tag[] } | null) => setTagOptions(data?.tags ?? []))
  }, [])

  async function refreshPrices() {
    const res = await fetch('/api/settings/model-pricing')
    if (res.ok) {
      const json: { prices: ModelPricing[] } = await res.json()
      setPrices(json.prices)
    }
  }

  useEffect(() => {
    void refreshPrices()
    fetch('/api/settings/model-ratings')
      .then((res) => (res.ok ? res.json() : null))
      .then((json: { ratings: ModelStats[] } | null) => setRatings(json?.ratings ?? []))
  }, [])

  const selectedEntry = entries.find((entry) => entry.id === entryId) ?? null
  const selectedStats = selectedEntry
    ? ratings.find((row) => statsKey(row.provider_type, row.model_name) === statsKey(selectedEntry.provider_type, selectedEntry.vision_model))
    : undefined
  const currentPrice = result
    ? prices.find((row) => row.provider_type === result.provider_type && row.model_name === result.model_name)
    : undefined

  async function handleRun() {
    setRunning(true)
    setRunError(null)
    setResult(null)
    setPreparing(null)
    setSelectedTags([])
    setTagVotes({})
    setEditingPrice(false)
    try {
      // Show the images/prompt as soon as they're ready, without waiting for
      // the (potentially slow) model call below (user request).
      try {
        const prepRes = await fetch(`/api/files/${file.id}/tag-lab/prepare`, { method: 'POST' })
        if (prepRes.ok) {
          setPreparing(await prepRes.json())
        }
      } catch {
        // Best-effort -- if this fails, the run request below still shows
        // the same error handling it always has.
      }

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
      setPreparing(null)
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

  async function handleVote(tag: SelectedTag, vote: 1 | -1) {
    if (!result || !tag.tag_id) {
      return
    }
    const nextVote: 1 | -1 | null = tagVotes[tag.tag_id] === vote ? null : vote
    try {
      const res = await fetch(`/api/tag-lab/runs/${result.run_id}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag_id: tag.tag_id, display_name: tag.display_name, vote: nextVote }),
      })
      if (!res.ok) {
        return
      }
      setTagVotes((current) => {
        const next = { ...current }
        if (nextVote === null) {
          delete next[tag.tag_id as string]
        } else {
          next[tag.tag_id as string] = nextVote
        }
        return next
      })
    } catch {
      // Best-effort -- a failed vote just leaves the button unchanged.
    }
  }

  function startEditPrice() {
    setPriceDraft({
      input: currentPrice?.input_per_million?.toString() ?? '',
      output: currentPrice?.output_per_million?.toString() ?? '',
    })
    setEditingPrice(true)
  }

  async function handleSavePrice() {
    if (!result) {
      return
    }
    const input = Number.parseFloat(priceDraft.input)
    const output = Number.parseFloat(priceDraft.output)
    if (Number.isNaN(input) || Number.isNaN(output)) {
      return
    }
    setSavingPrice(true)
    try {
      const res = await fetch('/api/settings/model-pricing', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider_type: result.provider_type,
          model_name: result.model_name,
          input_per_million: input,
          output_per_million: output,
        }),
      })
      if (res.ok) {
        await refreshPrices()
        setEditingPrice(false)
      }
    } finally {
      setSavingPrice(false)
    }
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
          run_id: result.run_id,
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
        {selectedEntry && (
          <p className="tag-lab__model-stats">
            <span title={t('tagLab.statsLikeRatioTooltip')}>
              👍{' '}
              {selectedStats && selectedStats.likes + selectedStats.dislikes > 0
                ? t('tagLab.statsLikeRatioValue', {
                    percent: Math.round((selectedStats.likes / (selectedStats.likes + selectedStats.dislikes)) * 100),
                  })
                : t('tagLab.statsNoData')}
            </span>
            <span title={t('tagLab.statsUnchangedTooltip')}>
              ✅ {selectedStats?.applied_unchanged_count ?? 0}
            </span>
            <span title={t('tagLab.statsChangedTooltip')}>
              ✏️ {selectedStats?.applied_changed_count ?? 0}
            </span>
            <span title={t('tagLab.statsNotAppliedTooltip')}>
              🚫 {selectedStats?.not_applied_count ?? 0}
            </span>
          </p>
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

        {preparing && !result && (
          <div className="convert-dialog__results">
            <p className="convert-dialog__hint">{t('tagLab.imagesTitle')}</p>
            <div className="tag-lab__images">
              {preparing.images.map((image, index) => (
                <img
                  key={index}
                  src={image.data_url}
                  alt=""
                  className="tag-lab__image"
                  onClick={() => setZoomedImage(image.data_url)}
                />
              ))}
            </div>
            <details className="tag-lab__details">
              <summary>{t('tagLab.promptTitle')}</summary>
              <pre className="tag-lab__pre">{preparing.prompt}</pre>
            </details>
          </div>
        )}

        {result && (
          <div className="convert-dialog__results">
            <p className="convert-dialog__hint">{t('tagLab.imagesTitle')}</p>
            <div className="tag-lab__images">
              {result.images.map((image, index) => (
                <img
                  key={index}
                  src={image.data_url}
                  alt=""
                  className="tag-lab__image"
                  onClick={() => setZoomedImage(image.data_url)}
                />
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

            <p className="tag-lab__price">
              {!editingPrice ? (
                <>
                  {currentPrice?.input_per_million != null && currentPrice.output_per_million != null
                    ? t('tagLab.pricePerMillion', {
                        input: currentPrice.input_per_million,
                        output: currentPrice.output_per_million,
                      })
                    : t('tagLab.priceUnavailable')}
                  {currentPrice && (
                    <span className="tag-lab__price-source">
                      {' '}
                      ({t(`tagLab.priceSource.${currentPrice.source}`)})
                    </span>
                  )}
                  <button
                    type="button"
                    className="tag-lab__price-edit"
                    onClick={startEditPrice}
                    aria-label={t('tagLab.editPrice')}
                    title={t('tagLab.editPrice')}
                  >
                    <Pencil size={12} />
                  </button>
                </>
              ) : (
                <span className="tag-lab__price-form">
                  <input
                    type="number"
                    step="any"
                    className="tag-lab__price-input"
                    placeholder={t('tagLab.priceInputPlaceholder')}
                    value={priceDraft.input}
                    onChange={(event) => setPriceDraft((current) => ({ ...current, input: event.target.value }))}
                  />
                  <input
                    type="number"
                    step="any"
                    className="tag-lab__price-input"
                    placeholder={t('tagLab.priceOutputPlaceholder')}
                    value={priceDraft.output}
                    onChange={(event) => setPriceDraft((current) => ({ ...current, output: event.target.value }))}
                  />
                  <button
                    type="button"
                    className="tag-lab__price-save"
                    onClick={() => void handleSavePrice()}
                    disabled={savingPrice}
                  >
                    {t('tagLab.priceSave')}
                  </button>
                  <button type="button" className="tag-lab__price-cancel" onClick={() => setEditingPrice(false)}>
                    {t('convertDialog.cancel')}
                  </button>
                </span>
              )}
            </p>

            <details className="tag-lab__details">
              <summary>{t('tagLab.rawResponseTitle')}</summary>
              <pre className="tag-lab__pre">{result.raw_response ?? ''}</pre>
            </details>

            <details className="tag-lab__details">
              <summary>{t('tagLab.rawJsonTitle')}</summary>
              <pre className="tag-lab__pre">{JSON.stringify(result.raw_full_response ?? {}, null, 2)}</pre>
            </details>

            <h3 className="tag-lab__section-title">{t('tagLab.suggestedTagsTitle')}</h3>
            {selectedTags.length === 0 && <p className="file-info-panel__tags-empty">{t('tagLab.noTagsSuggested')}</p>}
            {selectedTags.length > 0 && (
              <ul className="file-info-panel__tags-list">
                {selectedTags.map((tag) => (
                  <li key={tag.display_name} className="file-info-panel__tags-row">
                    <span className="file-info-panel__tags-name">{tag.display_name}</span>
                    <span className="file-info-panel__tags-score">{tag.score}%</span>
                    {tag.source === 'model' && tag.tag_id && (
                      <span className="tag-lab__vote">
                        <button
                          type="button"
                          className={`tag-lab__vote-btn${tagVotes[tag.tag_id] === 1 ? ' tag-lab__vote-btn--active-like' : ''}`}
                          aria-label={t('tagLab.like')}
                          title={t('tagLab.like')}
                          onClick={() => void handleVote(tag, 1)}
                        >
                          <ThumbsUp size={12} />
                        </button>
                        <button
                          type="button"
                          className={`tag-lab__vote-btn${tagVotes[tag.tag_id] === -1 ? ' tag-lab__vote-btn--active-dislike' : ''}`}
                          aria-label={t('tagLab.dislike')}
                          title={t('tagLab.dislike')}
                          onClick={() => void handleVote(tag, -1)}
                        >
                          <ThumbsDown size={12} />
                        </button>
                      </span>
                    )}
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
                {tagOptions.map((option) => (
                  <option key={option.id} value={option.display_name} />
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

      {zoomedImage && (
        <div
          className="tag-lab__zoom-overlay"
          onClick={(event) => {
            event.stopPropagation()
            setZoomedImage(null)
          }}
        >
          <img src={zoomedImage} alt="" className="tag-lab__zoom-image" />
        </div>
      )}
    </div>
  )
}
