import { MapContainer, TileLayer, CircleMarker, Polyline, Circle, Tooltip, Rectangle } from 'react-leaflet'
import { bounds, lake, clusters, obstacles, pass2Waypoints } from '../mockData'

const CONF_COLORS = { HIGH: '#22c55e', MEDIUM: '#f59e0b', LOW: '#ef4444' }
const OBS_COLORS  = { power_line: '#ef4444', fence_line: '#f97316', tower: '#dc2626' }

function ClusterMarkers({ selected, onSelect }) {
  return clusters.map(c => (
    <CircleMarker
      key={c.id}
      center={[c.lat, c.lon]}
      radius={14}
      pathOptions={{
        color: selected === c.id ? '#fff' : CONF_COLORS[c.confidence],
        fillColor: CONF_COLORS[c.confidence],
        fillOpacity: 0.85,
        weight: selected === c.id ? 3 : 1.5,
      }}
      eventHandlers={{ click: () => onSelect(c.id) }}
    >
      <Tooltip permanent direction="top" offset={[0, -16]} className="cluster-tip">
        <span style={{ fontWeight: 700, fontSize: 13 }}>{c.count}</span>
      </Tooltip>
    </CircleMarker>
  ))
}

function ObstacleOverlay() {
  const powerPoints = obstacles.filter(o => o.type === 'power_line').map(o => [o.lat, o.lon])
  const fencePosts  = obstacles.filter(o => o.type === 'fence_line')
  const towers      = obstacles.filter(o => o.type === 'tower')

  return (
    <>
      {powerPoints.length > 1 && (
        <Polyline positions={powerPoints} pathOptions={{ color: '#ef4444', weight: 2.5, dashArray: '6 4', opacity: 0.8 }}>
          <Tooltip sticky>Power line corridor — OSM confirmed</Tooltip>
        </Polyline>
      )}
      {fencePosts.map(o => (
        <CircleMarker key={o.id} center={[o.lat, o.lon]} radius={3}
          pathOptions={{ color: '#f97316', fillColor: '#f97316', fillOpacity: 0.7, weight: 1 }}>
          <Tooltip sticky>{o.note}</Tooltip>
        </CircleMarker>
      ))}
      {towers.map(o => (
        <Circle key={o.id} center={[o.lat, o.lon]} radius={o.exclusion_radius_m}
          pathOptions={{ color: '#dc2626', fillColor: '#dc2626', fillOpacity: 0.15, weight: 2, dashArray: '4 4' }}>
          <Tooltip sticky><strong>HAZARD: {o.note}</strong></Tooltip>
        </Circle>
      ))}
    </>
  )
}

function LakeOverlay() {
  return (
    <Circle center={lake.center} radius={lake.radius_m}
      pathOptions={{ color: '#38bdf8', fillColor: '#0ea5e9', fillOpacity: 0.3, weight: 1.5 }}>
      <Tooltip>{lake.label}</Tooltip>
    </Circle>
  )
}

function PropertyBoundary() {
  const sw = [bounds.south, bounds.west]
  const ne = [bounds.north, bounds.east]
  return <Rectangle bounds={[sw, ne]} pathOptions={{ color: '#64748b', fillOpacity: 0, weight: 2, dashArray: '8 4' }} />
}

function Pass2WaypointMarkers() {
  return pass2Waypoints.map(wp => (
    <CircleMarker key={wp.id} center={[wp.lat, wp.lon]} radius={6}
      pathOptions={{ color: wp.locked ? '#dc2626' : '#818cf8', fillColor: wp.locked ? '#dc2626' : '#818cf8', fillOpacity: 0.6, weight: 1.5 }}>
      <Tooltip sticky>WP{wp.index} — {wp.safe_alt_m}m AGL {wp.locked ? '🔒 LOCKED' : '✓ READY'}</Tooltip>
    </CircleMarker>
  ))
}

export default function PropertyMap({ selectedCluster, onSelectCluster }) {
  return (
    <MapContainer
      center={bounds.center}
      zoom={17}
      style={{ flex: 1, width: '100%' }}
      zoomControl={true}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />
      <PropertyBoundary />
      <LakeOverlay />
      <ObstacleOverlay />
      <Pass2WaypointMarkers />
      <ClusterMarkers selected={selectedCluster} onSelect={onSelectCluster} />
    </MapContainer>
  )
}
