import { useState, useMemo, useEffect, useCallback } from 'react'
import PropertyMap from './components/PropertyMap'
import AlertPanel from './components/AlertPanel'
import StatusBar from './components/StatusBar'
import TargetQueue from './components/TargetQueue'
import { bounds as mockBounds, lake as mockLake, clusters as mockClusters, obstacles as mockObstacles, pass2WaypointsBase } from './mockData'

// ── mock fallback ─────────────────────────────────────────────────────────────
// Used when the API server isn't running (demo / offline mode)
function buildMockMission() {
  return {
    mission_id:   'demo',
    status:       'pass1_complete',
    bounds:       { ...mockBounds, center: mockBounds.center },
    lake:         mockLake,
    clusters:     mockClusters,
    obstacles:    mockObstacles,
    waypoints:    pass2WaypointsBase,
    resolutions:  {},
    _source:      'mock',
  }
}

export default function App() {
  const [mission, setMission]             = useState(() => buildMockMission())
  const [isLive, setIsLive]               = useState(false)
  const [selectedCluster, setSelectedCluster] = useState(null)
  const [resolvedObstacles, setResolvedObstacles] = useState({})
  const [launchState, setLaunchState]     = useState(null)

  // ── fetch live mission on mount ─────────────────────────────────────────────
  useEffect(() => {
    fetch('/api/mission')
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => {
        setMission(data)
        setIsLive(true)
        // Seed resolutions from server (persisted across refreshes)
        if (data.resolutions) setResolvedObstacles(data.resolutions)
      })
      .catch(() => {
        // API not reachable — stay in demo mode with mockData
        setIsLive(false)
      })
  }, [])

  // ── resolve obstacle: update local state + persist to server ────────────────
  const handleResolve = useCallback((obstacleId, decision) => {
    setResolvedObstacles(r => ({ ...r, [obstacleId]: decision }))
    if (isLive) {
      fetch('/api/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ obstacle_id: obstacleId, decision, mission_id: mission.mission_id }),
      }).catch(() => {})
    }
  }, [isLive, mission.mission_id])

  // ── derive waypoints reactively from base + resolutions ────────────────────
  // In live mode the server returns pre-derived waypoints, but we still apply
  // client-side resolution overrides so the UI reacts instantly without a refetch.
  const waypoints = useMemo(() => {
    const base = mission.waypoints ?? []
    return base.map(wp => {
      if (!wp.locked_by) return wp
      const resolution = resolvedObstacles[wp.locked_by]
      if (resolution === 'safe')   return { ...wp, locked: false, lock_reason: null }
      if (resolution === 'hazard') return { ...wp, locked: true,  lock_reason: `Confirmed hazard — route excluded (${wp.locked_by})` }
      return wp
    })
  }, [mission.waypoints, resolvedObstacles])

  const pendingAlerts = (mission.obstacles ?? []).filter(
    o => o.confidence === 'LOW' && !resolvedObstacles[o.id]
  )
  const readyWaypoints = waypoints.filter(wp => !wp.locked)
  const pass2Ready     = pendingAlerts.length === 0 && readyWaypoints.length > 0

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
        isLive={isLive}
        missionId={mission.mission_id}
      />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <PropertyMap
            selectedCluster={selectedCluster}
            onSelectCluster={setSelectedCluster}
            waypoints={waypoints}
            bounds={mission.bounds}
            lake={mission.lake}
            clusters={mission.clusters ?? []}
            obstacles={mission.obstacles ?? []}
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
          obstacles={mission.obstacles ?? []}
          resolvedObstacles={resolvedObstacles}
          onResolve={handleResolve}
        />
      </div>
    </div>
  )
}
