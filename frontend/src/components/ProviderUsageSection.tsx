import { useTranslation } from 'react-i18next'
import type { ModelPricing, ProviderType, ProviderUsageSummary } from '../types/api'

type UsageTotals = Omit<ProviderUsageSummary, 'provider_type' | 'model_name' | 'total_items'>

function addNullable(a: number | null, b: number | null): number | null {
  return a === null && b === null ? null : (a ?? 0) + (b ?? 0)
}

function sumRows(rows: ProviderUsageSummary[]): UsageTotals {
  return rows.reduce<UsageTotals>(
    (acc, row) => ({
      call_count: acc.call_count + row.call_count,
      success_count: acc.success_count + row.success_count,
      total_tokens_in: addNullable(acc.total_tokens_in, row.total_tokens_in),
      total_tokens_out: addNullable(acc.total_tokens_out, row.total_tokens_out),
      total_estimated_cost_usd: addNullable(acc.total_estimated_cost_usd, row.total_estimated_cost_usd),
      reported_cost_usd: addNullable(acc.reported_cost_usd, row.reported_cost_usd),
      estimated_cost_usd: addNullable(acc.estimated_cost_usd, row.estimated_cost_usd),
      last_used_at: acc.last_used_at > row.last_used_at ? acc.last_used_at : row.last_used_at,
    }),
    {
      call_count: 0,
      success_count: 0,
      total_tokens_in: null,
      total_tokens_out: null,
      total_estimated_cost_usd: null,
      reported_cost_usd: null,
      estimated_cost_usd: null,
      last_used_at: '',
    },
  )
}

// Read-only usage table, grouped by provider with a subtotal each and a grand
// total. A cost is either what the provider reported for the call
// ("actual") or tokens x the model's price ("estimate"); the cell shows the
// total and, under it, that split. Also the only place a price is visible
// for a model that's no longer configured (prices are kept for past usage).
export function ProviderUsageSection({ usage, prices }: { usage: ProviderUsageSummary[]; prices: ModelPricing[] }) {
  const { t } = useTranslation()
  const notAvailable = t('providerUsage.notAvailable')

  const groups: { providerType: ProviderType; rows: ProviderUsageSummary[] }[] = []
  for (const row of usage) {
    const group = groups.find((g) => g.providerType === row.provider_type)
    if (group) group.rows.push(row)
    else groups.push({ providerType: row.provider_type, rows: [row] })
  }

  function priceText(row: ProviderUsageSummary): string {
    const price = prices.find((p) => p.provider_type === row.provider_type && p.model_name === row.model_name)
    if (price?.input_per_million == null || price.output_per_million == null) return notAvailable
    return t('providerSettings.priceShort', { input: price.input_per_million, output: price.output_per_million })
  }

  function costCell(totals: UsageTotals) {
    if (totals.total_estimated_cost_usd == null) return notAvailable
    // Calls logged before the source was recorded only count toward the total.
    const unknown = totals.total_estimated_cost_usd - (totals.reported_cost_usd ?? 0) - (totals.estimated_cost_usd ?? 0)
    const parts = [
      totals.reported_cost_usd != null && t('providerUsage.costReported', { cost: totals.reported_cost_usd.toFixed(4) }),
      totals.estimated_cost_usd != null &&
        t('providerUsage.costEstimated', { cost: totals.estimated_cost_usd.toFixed(4) }),
      unknown >= 0.00005 && t('providerUsage.costUnknown', { cost: unknown.toFixed(4) }),
    ].filter(Boolean)
    return (
      <>
        ${totals.total_estimated_cost_usd.toFixed(4)}
        {parts.length > 0 && <span className="provider-usage-table__cost-split">{parts.join(' · ')}</span>}
      </>
    )
  }

  function cells(totals: UsageTotals) {
    return (
      <>
        <td>{t('providerUsage.callsValue', { success: totals.success_count, total: totals.call_count })}</td>
        <td>{totals.total_tokens_in ?? notAvailable}</td>
        <td>{totals.total_tokens_out ?? notAvailable}</td>
        <td>{costCell(totals)}</td>
      </>
    )
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
            {groups.map(({ providerType, rows }) => {
              const totals = sumRows(rows)
              return (
                <tbody key={providerType}>
                  <tr className="provider-usage-table__group">
                    <td>{t(`providers.${providerType}`)}</td>
                    {cells(totals)}
                    <td />
                    <td>{new Date(totals.last_used_at).toLocaleString()}</td>
                  </tr>
                  {rows.map((row) => (
                    <tr key={`${row.provider_type}-${row.model_name}`}>
                      <td className="provider-usage-table__model">{row.model_name ?? notAvailable}</td>
                      {cells(row)}
                      <td>{priceText(row)}</td>
                      <td>{new Date(row.last_used_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              )
            })}
            <tfoot>
              <tr className="provider-usage-table__total">
                <td>{t('providerUsage.total')}</td>
                {cells(sumRows(usage))}
                <td />
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  )
}
