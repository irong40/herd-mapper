import { useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, Circle, Tooltip, Rectangle } from 'react-leaflet'
import { divIcon } from 'leaflet'
import { bounds, lake, clusters, obstacles, pass2Waypoints } from '../mockData'

const CONF_COLORS = { HIGH: '#22c55e', MEDIUM: '#f59e0b', LOW: '#ef4444' }

function ClusterMarkers({ selected, onSelect }) {
  return clusters.map(c => {
    const color = CONF_COLORS[c.confidence]
    const isSelected = selected === c.id
    const icon = divIcon({
      html: `<div class="hm-cluster ${isSelected ? 'hm-cluster--selected hm-cluster--pulse' : ''}" style="--c:${color}"><span>${c.count}</span></div>`,
      className: '',
      iconSize: [46, 46],
      iconAnchor: [23, 23],
    })
    return (
      <Marker key={c.id} position={[c.lat, c.lon]} icon={icon} eventHandlers={{ click: () => onSelect(c.id) }}>
        <Tooltip direction="top" offset={[0, -26]} opacity={1}>
          <strong>{c.count} deer</strong> · {c.confidence} · {c.id}
        </Tooltip>
      </Marker>
    )
  })
}

function Pass2WaypointMarkers() {
  return pass2Waypoints.map(wp => {
    const color = wp.locked ? '#ef4444' : '#818cf8'
    const icon = divIcon({
      html: `<div class="hm-wp" style="--c:${color}">
               <div class="hm-wp-h"></div>
               <div class="hm-wp-v"></div>
               <div class="hm-wp-ring"></div>
               <div class="hm-wp-dot"></div>
             </div>`,
      className: '',
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    })
    return (
      <Marker key={wp.id} position={[wp.lat, wp.lon]} icon={icon}>
        <Tooltip direction="top" offset={[0, -14]} opacity={1}>
          WP{wp.index} · {wp.safe_alt_m}m AGL · {wp.locked ? 'LOCKED' : 'READY'}
        </Tooltip>
      </Marker>
    )
  })
}

function ObstacleOverlay() {
  const powerPoints = obstacles.filter(o => o.type === 'power_line').map(o => [o.lat, o.lon])
  const fencePosts  = obstacles.filter(o => o.type === 'fence_line')
  const towers      = obstacles.filter(o => o.type === 'tower')

  const fenceIcon = useMemo(() => divIcon({
    html: `<div style="width:7px;height:7px;border-radius:50%;background:#f97316;border:1px solid rgba(249,115,22,0.5);box-shadow:0 0 6px #f97316aa"></div>`,
    className: '',
    iconSize: [7, 7],
    iconAnchor: [3.5, 3.5],
  }), [])

  return (
    <>
      {powerPoints.length > 1 && (
        <Polyline positions={powerPoints} pathOptions={{ color: '#ef4444', weight: 2, dashArray: '8 5', opacity: 0.7 }}>
          <Tooltip sticky opacity={1}>Power line corridor — OSM confirmed</Tooltip>
        </Polyline>
      )}
      {fencePosts.map(o => (
        <Marker key={o.id} position={[o.lat, o.lon]} icon={fenceIcon}>
          <Tooltip sticky opacity={1}>{o.note}</Tooltip>
        </Marker>
      ))}
      {towers.map(o => (
        <Circle key={o.id} center={[o.lat, o.lon]} radius={o.exclusion_radius_m}
          pathOptions={{ color: '#dc2626', fillColor: '#dc2626', fillOpacity: 0.08, weight: 1.5, dashArray: '5 4' }}>
          <Tooltip sticky opacity={1}><strong>HAZARD</strong> · {o.note} · {o.exclusion_radius_m}m exclusion</Tooltip>
        </Circle>
      ))}
    </>
  )
}

function LakeOverlay() {
  return (
    <Circle center={lake.center} radius={lake.radius_m}
      pathOptions={{ color: '#38bdf8', fillColor: '#0ea5e9', fillOpacity: 0.18, weight: 1 }}>
      <Tooltip opacity={1}>{lake.label}</Tooltip>
    </Circle>
  )
}

function PropertyBoundary() {
  const sw = [bounds.south, bounds.west]
  const ne = [bounds.north, bounds.east]
  return (
    <Rectangle bounds={[sw, ne]}
      pathOptions={{ color: '#475569', fillOpacity: 0, weight: 1.5, dashArray: '10 6' }} />
  )
}

export default function PropertyMap({ selectedCluster, onSelectCluster }) {
  return (
    <MapContainer
      center={bounds.center}
      zoom={17}
      style={{ flex: 1, width: '100%' }}
      zoomControl={true}
    >
      {/* Satellite base */}
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        attribution="Tiles &copy; Esri"
        maxZoom={20}
      />
      {/* Dark label overlay */}
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png"
        attribution=""
        opacity={0.65}
      />
      <PropertyBoundary />
      <LakeOverlay />
      <ObstacleOverlay />
      <Pass2WaypointMarkers />
      <ClusterMarkers selected={selectedCluster} onSelect={onSelectCluster} />
    </MapContainer>
  )
}
