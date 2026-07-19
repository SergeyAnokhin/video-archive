import { useBackendHealth } from '../hooks/useBackendHealth'
import { useBackendStats } from '../hooks/useBackendStats'
import { BackendStatusDot } from './BackendStatusDot'
import { BackendResourceMeter } from './BackendResourceMeter'
import './BackendHealthWidget.css'

/** Groups the top-bar status dot with the resource meter (chat request
 * 2026-07-19) so they share a single health/stats polling pair instead of
 * each component polling independently. */
export function BackendHealthWidget() {
  const health = useBackendHealth()
  const stats = useBackendStats(health)

  return (
    <div className="backend-health-widget">
      <BackendStatusDot health={health} />
      {stats && <BackendResourceMeter stats={stats} />}
    </div>
  )
}
