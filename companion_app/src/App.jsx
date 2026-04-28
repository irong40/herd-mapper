import { useState, useMemo, useEffect, useCallback } from 'react'
import PropertyMap from './components/PropertyMap'
import AlertPanel from './components/AlertPanel'
import StatusBar from './components/StatusBar'
import TargetQueue from './components/TargetQueue'
import ScoutSummary from './components/ScoutSummary'
import { bounds as mockBounds, lake as mockLake, clusters as mockClusters, obstacles as mockObstacles, pass2WaypointsBase } from './mockData'

// ── mock fallback ─────────────────────────────────────────────────────────────
// Used when the API server isn't running (demo / offline mode)
function buildMockMission() {
  // Toggle mission_type to 'scout' to preview scout mode UI locally
  const DEMO_MODE = 'census' // 'census' | 'scout'
  if (DEMO_MODE === 'scout') {
    return {
      mission_id:       'demo_scout',
      mission_type:     'scout',
      drone:            'M4E',
      status:           'scout_complete',
      bounds:           { ...mockBounds, center: mockBounds.center },
      lake:             mockLake,
      clusters:         [],
      obstacles:        mockObstacles,
      waypoints:        [],
      resolutions:      {},
      agl_range:        { min_m: 15, max_m: 41 },
      obstacle_summary: { fence_line: 70, power_line: 11, tower: 1 },
      _source:          'mock',
    }
  }
  return {
    mission_id:   'demo',
    mission_type: 'census',
    drone:        'M4T',
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
  const [mission, setMission]                 = useState(() => buildMockMission())
  const [isLive, setIsLive]                   = useState(false)
  const [selectedCluster, setSelectedCluster] = useState(null)
  const [resolvedObstacles, setResolvedObstacles] = useState({})
  const [launchState, setLaunchState]         = useState(null)

  const isScouting = mission.mission_type === 'scout'

  // ── fetch live mission on mount ─────────────────────────────────────────────
  // URL params:
  //   ?scout=<property_id>       → scout mode  (e.g. ?scout=demo)
  //   ?mission=<mission_id>      → census mode (e.g. ?mission=demo)
  //   (no params)                → census mode, mission id 'demo'
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const scoutProp = params.get('scout')
    const missionId = params.get('mission') || 'demo'
    const url = scoutProp ? `/api/scout/${scoutProp}` : `/api/mission?id=${missionId}`

    fetch(url)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json() })
      .then(data => {
        setMission(data)
        setIsLive(true)
        if (data.resolutions) setResolvedObstacles(data.resolutions)
      })
      .catch(() => {
        setIsLive(false)
      })
  }, [])

  // ── resolve obstacle ────────────────────────────────────────────────────────
  const handleResolve = useCallback((obstacleId, decision) => {
    setResolvedObstacles(r => ({ ...r, [obstacleId]: decision }))
    if (isLive) {
      fetch('/api/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          obstacle_id: obstacleId,
          decision,
          mission_id:  mission.mission_id,
          property_id: mission.property_id ?? null,
        }),
      }).catch(() => {})
    }
  }, [isLive, mission.mission_id, mission.property_id])

  // ── derive waypoints (census mode only) ────────────────────────────────────
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
  const readyWaypoints  = waypoints.filter(wp => !wp.locked)
  const pass2Ready      = !isScouting && pendingAlerts.length === 0 && readyWaypoints.length > 0
  const clusterCount    = (mission.clusters ?? []).length
  const totalAnimals    = (mission.clusters ?? []).reduce((s, c) => s + c.count, 0)
  const propertyName    = mission.bounds?.name ?? null
  const scoutComplete   = isScouting && pendingAlerts.length === 0

  function handleLaunch() {
    if (!pass2Ready || launchState) return
    setLaunchState('executing')
    setTimeout(() => setLaunchState('complete'), 3200)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw' }}>
      <StatusBar
        isScouting={isScouting}
        drone={mission.drone}
        waypoints={waypoints}
        pendingAlerts={pendingAlerts}
        pass2Ready={pass2Ready}
        scoutComplete={scoutComplete}
        launchState={launchState}
        isLive={isLive}
        missionId={mission.mission_id}
        propertyName={propertyName}
        clusterCount={clusterCount}
        totalAnimals={totalAnimals}
        obstacleCount={(mission.obstacles ?? []).length}
      />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <PropertyMap
            selectedCluster={selectedCluster}
            onSelectCluster={setSelectedCluster}
            waypoints={isScouting ? [] : waypoints}
            bounds={mission.bounds}
            lake={mission.lake}
            clusters={mission.clusters ?? []}
            obstacles={mission.obstacles ?? []}
          />
          {isScouting
            ? <ScoutSummary
                obstacles={mission.obstacles ?? []}
                aglRange={mission.agl_range}
                obstacleSummary={mission.obstacle_summary}
                pendingAlerts={pendingAlerts}
                scoutComplete={scoutComplete}
              />
            : <TargetQueue
                selectedCluster={selectedCluster}
                onSelect={setSelectedCluster}
                waypoints={waypoints}
                pass2Ready={pass2Ready}
                launchState={launchState}
                onLaunch={handleLaunch}
              />
          }
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
