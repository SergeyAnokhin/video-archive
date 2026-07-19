import { useTranslation } from 'react-i18next'
import type { BackendHealth } from '../hooks/useBackendHealth'
import './BackendStatusDot.css'

interface BackendStatusDotProps {
  health: BackendHealth
}

const LABEL_KEY: Record<Exclude<BackendHealth, 'checking'>, string> = {
  online: 'topBar.backendOnline',
  slow: 'topBar.backendSlow',
  offline: 'topBar.backendOffline',
}

/** Small pulsing dot next to the app title (chat request 2026-07-19): green
 * and pulsing while the backend answers `/api/health` quickly, amber and
 * pulsing faster while it's slow to respond but not yet given up on (busy,
 * not down -- chat request 2026-07-19 follow-up), red once a poll
 * definitively fails. No visible label by design -- the exact state is in
 * the `title` tooltip only. */
export function BackendStatusDot({ health }: BackendStatusDotProps) {
  const { t } = useTranslation()
  const label = health === 'checking' ? undefined : t(LABEL_KEY[health])

  return (
    <span
      className={`backend-status-dot backend-status-dot--${health}`}
      title={label}
      role="status"
      aria-label={label}
    />
  )
}
