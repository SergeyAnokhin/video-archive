import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { ModelPricing } from '../types/api'

export function ModelPricingSection({ prices, onRefresh }: { prices: ModelPricing[]; onRefresh: () => Promise<void> }) {
  const { t } = useTranslation()
  const [refreshing, setRefreshing] = useState(false)
  const [refreshResult, setRefreshResult] = useState<{ updated: string[]; not_found: string[] } | null>(null)

  async function handleSavePrice(row: ModelPricing, changes: { input_per_million?: number; output_per_million?: number }) {
    const body = {
      provider_type: row.provider_type,
      model_name: row.model_name,
      input_per_million: row.input_per_million ?? 0,
      output_per_million: row.output_per_million ?? 0,
      ...changes,
    }
    const saved = await tryApi('/api/settings/model-pricing', { method: 'PUT', body })
    if (saved !== null) await onRefresh()
  }

  async function handleRefreshOpenRouter() {
    setRefreshing(true)
    setRefreshResult(null)
    try {
      const json = await tryApi<{ updated: string[]; not_found: string[] }>(
        '/api/settings/model-pricing/refresh-openrouter',
        { method: 'POST' },
      )
      if (json) {
        setRefreshResult(json)
        await onRefresh()
      }
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('modelPricing.title')}</h3>
      <p className="settings-modal__hint">{t('modelPricing.hint')}</p>
      <div className="settings-modal__actions">
        <button type="button" className="settings-modal__option" onClick={() => void handleRefreshOpenRouter()} disabled={refreshing}>
          <RefreshCw size={14} /> {refreshing ? t('modelPricing.refreshing') : t('modelPricing.refreshOpenRouter')}
        </button>
      </div>
      {refreshResult && (
        <p className="settings-modal__hint">
          {t('modelPricing.refreshResult', { updated: refreshResult.updated.length, notFound: refreshResult.not_found.length })}
        </p>
      )}
      {prices.length === 0 ? (
        <p className="settings-modal__hint">{t('modelPricing.empty')}</p>
      ) : (
        <div className="provider-usage-table__wrap">
          <table className="provider-usage-table">
            <thead>
              <tr>
                <th>{t('modelPricing.colModel')}</th>
                <th>{t('modelPricing.colInput')}</th>
                <th>{t('modelPricing.colOutput')}</th>
                <th>{t('modelPricing.colSource')}</th>
                <th>{t('modelPricing.colUpdatedAt')}</th>
              </tr>
            </thead>
            <tbody>
              {prices.map((row) => (
                <tr key={`${row.provider_type}-${row.model_name}`}>
                  <td>
                    {t(`providers.${row.provider_type}`)} / {row.model_name}
                  </td>
                  <td>
                    <input
                      type="number"
                      step="any"
                      className="settings-modal__input"
                      defaultValue={row.input_per_million ?? ''}
                      onBlur={(event) => {
                        const value = Number.parseFloat(event.target.value)
                        if (!Number.isNaN(value)) void handleSavePrice(row, { input_per_million: value })
                      }}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="any"
                      className="settings-modal__input"
                      defaultValue={row.output_per_million ?? ''}
                      onBlur={(event) => {
                        const value = Number.parseFloat(event.target.value)
                        if (!Number.isNaN(value)) void handleSavePrice(row, { output_per_million: value })
                      }}
                    />
                  </td>
                  <td>{t(`modelPricing.source.${row.source}`)}</td>
                  <td>{new Date(row.updated_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
