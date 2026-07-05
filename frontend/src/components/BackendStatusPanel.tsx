import { useTranslation } from 'react-i18next'
import { useBackendStatus } from '../hooks/useBackendStatus'
import './BackendStatusPanel.css'

export function BackendStatusPanel() {
  const { t } = useTranslation()
  const status = useBackendStatus()

  return (
    <section className="backend-status" aria-live="polite">
      <h1 className="backend-status__title">{t('backendStatus.title')}</h1>

      {status.phase === 'loading' && (
        <p className="backend-status__message">{t('backendStatus.loading')}</p>
      )}

      {status.phase === 'error' && (
        <p className="backend-status__message backend-status__message--error">
          {t('backendStatus.error', { message: status.message })}
        </p>
      )}

      {status.phase === 'ready' && (
        <dl className="backend-status__grid">
          <dt>{t('backendStatus.api')}</dt>
          <dd className="backend-status__value--ok">
            {t('backendStatus.online')}
          </dd>

          <dt>{t('backendStatus.appVersion')}</dt>
          <dd>{status.appInfo.app_version}</dd>

          <dt>{t('backendStatus.database')}</dt>
          <dd>
            {t('backendStatus.schemaVersion', {
              version: status.appInfo.database.schema_version,
            })}
          </dd>

          <dt>{t('backendStatus.ffmpeg')}</dt>
          <dd
            className={
              status.appInfo.ffmpeg.available
                ? 'backend-status__value--ok'
                : 'backend-status__value--warning'
            }
          >
            {status.appInfo.ffmpeg.available
              ? t('backendStatus.ffmpegAvailable', {
                  version: status.appInfo.ffmpeg.version,
                })
              : t('backendStatus.ffmpegMissing')}
          </dd>
        </dl>
      )}
    </section>
  )
}
