import { useTranslation } from 'react-i18next'
import type { ModelPricing, ProviderUsageSummary } from '../types/api'

// Read-only usage table. Also the only place a price is visible for a model
// that's no longer configured (prices are kept for its past usage).
export function ProviderUsageSection({ usage, prices }: { usage: ProviderUsageSummary[]; prices: ModelPricing[] }) {
  const { t } = useTranslation()

  function priceText(row: ProviderUsageSummary): string {
    const price = prices.find((p) => p.provider_type === row.provider_type && p.model_name === row.model_name)
    if (price?.input_per_million == null || price.output_per_million == null) return t('providerUsage.notAvailable')
    return t('providerSettings.priceShort', { input: price.input_per_million, output: price.output_per_million })
  }

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
                <th>{t('providerUsage.colPrice')}</th>
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
                  <td>{priceText(row)}</td>
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
