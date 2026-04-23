import { useState, useMemo } from 'react'
import PropertyMap from './components/PropertyMap'
import AlertPanel from './components/AlertPanel'
import StatusBar from './components/StatusBar'
import TargetQueue from './components/TargetQueue'
import { obstacles, pass2WaypointsBase } from './mockData'

export default function App() {
  const [selectedCluster, setSelectedCluster] = useState(null)
  const [resolvedObstacles, setResolvedObstacles] = useState({})
  const [launchState, setLaunchState] = useState(null) // null | 'executing' | 'complete'

  // Derive waypoints: unlock any WP whose blocking obstacle was confirmed safe
  const waypoints = useMemo(() =>
    pass2WaypointsBase.map(wp => {
      if (!wp.locked_by) return wp
      const resolution = resolvedObstacles[wp.locked_by]
      if (resolution === 'safe') return { ...wp, locked: false, lock_reason: null }
      return wp
    }),
    [resolvedObstacles]
  )

  const pendingAlerts = obstacles.filter(
    o => o.confidence === 'LOW' && !resolvedObstacles[o.id]
  )
  const readyWaypoints = waypoints.filter(wp => !wp.locked)
  const pass2Ready = pendingAlerts.length === 0 && readyWaypoints.length > 0

  function handleResolve(id, decision) {
    setResolvedObstacles(r => ({ ...r, [id]: decision }))
  }

  function handleLaunch() {
    if (!pass2Ready || launchState) return
    setLaunchState('executing')
    setTimeout(() => setLaunchState('complete'), 3200)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw' }}>
      <StatusBar
        waypoints={waypoints}
        pendingAlerts={pendingAlerts}
        pass2Ready={pass2Ready}
        launchState={launchState}
      />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <PropertyMap
            selectedCluster={selectedCluster}
            onSelectCluster={setSelectedCluster}
            waypoints={waypoints}
          />
          <TargetQueue
            selectedCluster={selectedCluster}
            onSelect={setSelectedCluster}
            waypoints={waypoints}
            pass2Ready={pass2Ready}
            launchState={launchState}
            onLaunch={handleLaunch}
          />
        </div>
        <AlertPanel
          resolvedObstacles={resolvedObstacles}
          onResolve={handleResolve}
        />
      </div>
    </div>
  )
}
