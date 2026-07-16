import { Pencil, Play, Plus, Tags, ThumbsDown, ThumbsUp, X } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { fetchWithTimeout } from '../utils/fetchWithTimeout'
import { getRecentTags, recordRecentTag } from '../utils/recentTags'
import { buildTagSuggestions } from '../utils/tagSuggestions'
import type {
  FileEntry,
  ModelPricing,
  ModelStats,
  ProviderEntry,
  Tag,
  TaggingSettings,
  TagLabPreparedResult,
  TagLabRunResult,
} from '../types/api'
import { TagBadge } from './TagBadge'
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
  color?: string | null
  score: number
  source: 'model' | 'manual'
}

function normalizeName(name: string): string {
  return name.trim().toLowerCase()
}

function statsKey(providerType: string, modelName: string | null): string {
  return `${providerType}:${modelName ?? ''}`
}

// Defensive client-side ceiling on top of the backend's own
// `request_timeout_seconds` (user request -- the modal must never wait
// forever on "Ожидание ответа модели…", even if the root cause of an
// occasional hang, seen as a logged 200 with no UI update, turns out to be
// outside this component). The margin over the backend timeout leaves room
// for the backend's own timeout to fire and produce a normal HTTP error
// first, so this only fires when even that didn't happen.
const DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
const CLIENT_TIMEOUT_MARGIN_SECONDS = 15

// Shared by the success and error paths -- the model's raw reply must stay
// inspectable even when interpreting it failed (user request: written first,
// collapsed, so a parse failure is still self-diagnosable from what actually
// came back).
function RawResponseDetails({ rawResponse, rawFullResponse }: { rawResponse?: string | null; rawFullResponse?: unknown }) {
  const { t } = useTranslation()
  return (
    <>
      <details className="tag-lab__details">
        <summary>{t('tagLab.rawResponseTitle')}</summary>
        <pre className="tag-lab__pre">{rawResponse ?? ''}</pre>
      </details>

      <details className="tag-lab__details">
        <summary>{t('tagLab.rawJsonTitle')}</summary>
        <pre className="tag-lab__pre">{JSON.stringify(rawFullResponse ?? {}, null, 2)}</pre>
      </details>
    </>
  )
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
  const [runErrorRaw, setRunErrorRaw] = useState<{ raw_response?: string; raw_full_response?: unknown } | null>(null)
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
  const [requestTimeoutSeconds, setRequestTimeoutSeconds] = useState(DEFAULT_REQUEST_TIMEOUT_SECONDS)

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

  useEffect(() => {
    fetch('/api/tagging-settings')
      .then((res) => (res.ok ? res.json() : null))
      .then((data: TaggingSettings | null) => {
        if (data) {
          setRequestTimeoutSeconds(data.request_timeout_seconds)
        }
      })
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
    setRunErrorRaw(null)
    setResult(null)
    setPreparing(null)
    setSelectedTags([])
    setTagVotes({})
    setEditingPrice(false)
    const timeoutMs = (requestTimeoutSeconds + CLIENT_TIMEOUT_MARGIN_SECONDS) * 1000
    try {
      // Show the images/prompt as soon as they're ready, without waiting for
      // the (potentially slow) model call below (user request).
      try {
        const prepRes = await fetchWithTimeout(`/api/files/${file.id}/tag-lab/prepare`, { method: 'POST' }, timeoutMs)
        if (prepRes.ok) {
          setPreparing(await prepRes.json())
        }
      } catch {
        // Best-effort (including a timeout) -- if this fails, the run
        // request below still shows the same error handling it always has.
      }

      let res: Response
      try {
        res = await fetchWithTimeout(
          `/api/files/${file.id}/tag-lab/run`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider_entry_id: entryId }),
          },
          timeoutMs,
        )
      } catch (err) {
        // A defensive ceiling on top of the backend's own timeout (user
        // request -- this modal must never wait on "Ожидание ответа
        // модели…" forever, even if a hang's root cause turns out to be
        // outside this component). Distinct, recognizable message so a
        // future occurrence is diagnosable as "the client gave up waiting"
        // rather than a generic network error.
        if (err instanceof DOMException && err.name === 'AbortError') {
          throw new Error(t('tagLab.runTimedOut'))
        }
        throw err
      }
      if (!res.ok) {
        const json = await res.json().catch(() => null)
        const error = json?.detail?.error
        if (error?.raw_response || error?.raw_full_response) {
          setRunErrorRaw({ raw_response: error.raw_response, raw_full_response: error.raw_full_response })
        }
        throw new Error(error?.message ?? `HTTP ${res.status}`)
      }
      const data: TagLabRunResult = await res.json()
      setResult(data)
      setSelectedTags(
        data.tags
          .filter((tag) => tag.score > 0)
          .map((tag) => ({
            tag_id: tag.tag_id,
            display_name: tag.display_name,
            color: tag.color,
            score: tag.score,
            source: 'model',
          })),
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

  // `tag` is the matching pool entry when adding from a suggestion chip
  // (carries its real id/color, user request -- previously a suggestion
  // pick still went through the free-text path and lost both), omitted for
  // a genuinely free-typed name (falls back to TagBadge's hash color, same
  // as before).
  function addTag(displayName: string, tag?: Tag) {
    const trimmed = displayName.trim()
    if (!trimmed) {
      return
    }
    setSelectedTags((current) => {
      if (current.some((existing) => normalizeName(existing.display_name) === normalizeName(trimmed))) {
        return current
      }
      return [...current, { tag_id: tag?.id ?? null, display_name: trimmed, color: tag?.color, score: 100, source: 'manual' }]
    })
    recordRecentTag(trimmed)
    setTagInput('')
  }

  function handleAddTag(event: FormEvent) {
    event.preventDefault()
    addTag(tagInput)
  }

  // Suggestion ordering (user request, shared with QuickTagAdd/
  // FileInfoPanel): recently manually-added tags first, then the rest of
  // `tagOptions` (already usage-ordered, fetched once at up to 500 entries)
  // filtered to what's typed so far.
  const tagSuggestions = useMemo(() => {
    const query = tagInput.trim().toLowerCase()
    const filtered = query
      ? tagOptions.filter(
          (tag) => tag.tag_key.includes(query) || tag.display_name.toLowerCase().includes(query),
        )
      : tagOptions
    return buildTagSuggestions(getRecentTags(), filtered)
  }, [tagInput, tagOptions])

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
        {runErrorRaw && (
          <RawResponseDetails
            rawResponse={runErrorRaw.raw_response}
            rawFullResponse={runErrorRaw.raw_full_response}
          />
        )}

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

            <RawResponseDetails rawResponse={result.raw_response} rawFullResponse={result.raw_full_response} />

            <h3 className="tag-lab__section-title">{t('tagLab.suggestedTagsTitle')}</h3>
            {selectedTags.length === 0 && <p className="file-info-panel__tags-empty">{t('tagLab.noTagsSuggested')}</p>}
            {selectedTags.length > 0 && (
              <ul className="file-info-panel__tags-list">
                {selectedTags.map((tag) => (
                  <li key={tag.display_name} className="file-info-panel__tags-row">
                    <TagBadge
                      displayName={tag.display_name}
                      color={tag.color}
                      scoreLabel={`${tag.score}%`}
                      onRemove={() => handleRemoveTag(tag.display_name)}
                      removeLabel={t('library.tagsRemove', { name: tag.display_name })}
                    />
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
                  </li>
                ))}
              </ul>
            )}
            <div className="file-info-panel__tags-add-wrap">
              <form className="file-info-panel__tags-add" onSubmit={handleAddTag}>
                <input
                  type="text"
                  className="file-info-panel__tags-input"
                  placeholder={t('library.tagsAddPlaceholder')}
                  value={tagInput}
                  onChange={(event) => setTagInput(event.target.value)}
                />
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
              {tagSuggestions.length > 0 && (
                <div className="file-info-panel__tags-suggestions">
                  {tagSuggestions.map((option) => (
                    <TagBadge
                      key={option.id}
                      displayName={option.display_name}
                      color={option.color}
                      onClick={() => addTag(option.display_name, option)}
                    />
                  ))}
                </div>
              )}
            </div>

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
