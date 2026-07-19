import { useTranslation } from 'react-i18next'
import type { BackendHealth } from '../hooks/useBackendHealth'
import './BackendStatusDot.css'

interface BackendStatusDotProps {
  health: BackendHealth
}

/** Small pulsing dot next to the app title (chat request 2026-07-19): green
 * and pulsing while the backend answers `/api/health`, red once a poll
 * fails. No visible label by design -- the exact state is in the `title`
 * tooltip only. */
export function BackendStatusDot({ health }: BackendStatusDotProps) {
  const { t } = useTranslation()
  const label = health === 'checking' ? undefined : t(health === 'online' ? 'topBar.backendOnline' : 'topBar.backendOffline')

  return (
    <span
      className={`backend-status-dot backend-status-dot--${health}`}
      title={label}
      role="status"
      aria-label={label}
    />
  )
}
