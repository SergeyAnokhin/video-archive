import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ModelUsage } from '../types/api'

export function ModelUsageSection() {
  const { t } = useTranslation()
  const [usage, setUsage] = useState<ModelUsage[]>([])
  useEffect(() => { fetch('/api/settings/model-usage').then((res) => res.ok ? res.json() : { usage: [] }).then((data) => setUsage(data.usage ?? [])) }, [])
  return <section>
    <h3 className="settings-modal__section-title">{t('modelUsage.title')}</h3>
    {usage.length === 0 ? <p className="settings-modal__hint">{t('modelUsage.empty')}</p> : (
      <div className="settings-modal__table-wrap"><table className="settings-modal__table"><thead><tr><th>{t('modelUsage.model')}</th><th>{t('modelUsage.requests')}</th><th>{t('modelUsage.files')}</th><th>{t('modelUsage.batches')}</th></tr></thead><tbody>
        {usage.map((row) => <tr key={`${row.provider_name}-${row.model_name}`}><td>{row.provider_name} · {row.model_name}</td><td>{row.request_count}</td><td>{row.file_count}</td><td>{row.batch_count}</td></tr>)}
      </tbody></table></div>
    )}
  </section>
}
