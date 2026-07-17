import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { ProviderUsageSummary } from '../types/api'

export function ProviderUsageSection() {
  const { t } = useTranslation()
  const [usage, setUsage] = useState<ProviderUsageSummary[]>([])

  useEffect(() => {
    let cancelled = false
    tryApi<{ usage: ProviderUsageSummary[] }>('/api/settings/provider-usage').then((json) => {
      if (!cancelled) setUsage(json?.usage ?? [])
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('providerUsage.title')}</h3>
      <p className="settings-modal__hint">{t('providerUsage.hint')}</p>
      {usage.length === 0 ? (
        <p className="settings-modal__hint">{t('providerUsage.empty')}</p>
      ) : (
        <div className="provider-usage-table__wrap">
          <table className="provider-usage-table">
            <thead>
              <tr>
                <th>{t('providerUsage.colModel')}</th>
                <th>{t('providerUsage.colCalls')}</th>
                <th>{t('providerUsage.colTokensIn')}</th>
                <th>{t('providerUsage.colTokensOut')}</th>
                <th>{t('providerUsage.colCost')}</th>
                <th>{t('providerUsage.colLastUsed')}</th>
              </tr>
            </thead>
            <tbody>
              {usage.map((row) => (
                <tr key={`${row.provider_type}-${row.model_name}`}>
                  <td>
                    {t(`providers.${row.provider_type}`)} / {row.model_name ?? t('providerUsage.notAvailable')}
                  </td>
                  <td>{t('providerUsage.callsValue', { success: row.success_count, total: row.call_count })}</td>
                  <td>{row.total_tokens_in ?? t('providerUsage.notAvailable')}</td>
                  <td>{row.total_tokens_out ?? t('providerUsage.notAvailable')}</td>
                  <td>
                    {row.total_estimated_cost_usd != null
                      ? `$${row.total_estimated_cost_usd.toFixed(4)}`
                      : t('providerUsage.notAvailable')}
                  </td>
                  <td>{new Date(row.last_used_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
