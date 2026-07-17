import { Check, Copy, RefreshCw, Wifi, Smartphone, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { tryApi } from '../api/client'
import type { NetworkInfo } from '../types/api'

export function NetworkAccessSection() {
  const { t } = useTranslation()
  const [info, setInfo] = useState<NetworkInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [copiedAddress, setCopiedAddress] = useState<string | null>(null)

  const loadInfo = useCallback(async () => {
    setLoading(true)
    try {
      const info = await tryApi<NetworkInfo>('/api/app/network-info')
      if (info) {
        setInfo(info)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadInfo()
  }, [loadInfo])

  async function handleCopy(address: string) {
    await navigator.clipboard.writeText(address)
    setCopiedAddress(address)
    setTimeout(() => setCopiedAddress((current) => (current === address ? null : current)), 1500)
  }

  const addresses = info?.lan_addresses.map((ip) => `http://${ip}:${info.frontend_port}`) ?? []

  return (
    <section className="settings-modal__section">
      <h3 className="settings-modal__section-title">{t('networkAccess.title')}</h3>
      <p className="settings-modal__hint">{t('networkAccess.hint')}</p>

      <div className="network-access__header">
        <span className="network-access__label">{t('networkAccess.addressesTitle')}</span>
        <button
          type="button"
          className="settings-modal__option settings-modal__option--icon"
          onClick={() => void loadInfo()}
          disabled={loading}
          title={t('networkAccess.refresh')}
          aria-label={t('networkAccess.refresh')}
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {addresses.length > 0 ? (
        <div className="network-access__address-list">
          {addresses.map((address) => (
            <div className="network-access__address-row" key={address}>
              <code className="network-access__address">{address}</code>
              <button
                type="button"
                className="settings-modal__option settings-modal__option--icon"
                onClick={() => void handleCopy(address)}
                title={t('networkAccess.copy')}
                aria-label={t('networkAccess.copy')}
              >
                {copiedAddress === address ? <Check size={14} /> : <Copy size={14} />}
              </button>
            </div>
          ))}
        </div>
      ) : (
        !loading && <p className="settings-modal__hint settings-modal__hint--warning">{t('networkAccess.noAddresses')}</p>
      )}

      <div className="network-access__scenario">
        <h4 className="network-access__scenario-title">
          <Wifi size={14} /> {t('networkAccess.scenarioLanTitle')}
        </h4>
        <p className="settings-modal__hint">{t('networkAccess.scenarioLanText')}</p>
      </div>

      <div className="network-access__scenario">
        <h4 className="network-access__scenario-title">
          <Smartphone size={14} /> {t('networkAccess.scenarioHotspotTitle')}
        </h4>
        <p className="settings-modal__hint">{t('networkAccess.scenarioHotspotText')}</p>
      </div>

      <div className="network-access__scenario">
        <h4 className="network-access__scenario-title">
          <ShieldAlert size={14} /> {t('networkAccess.firewallTitle')}
        </h4>
        <p className="settings-modal__hint">{t('networkAccess.firewallText')}</p>
      </div>
    </section>
  )
}
