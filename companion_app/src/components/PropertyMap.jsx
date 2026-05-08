import { useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, Circle, Tooltip, Rectangle, useMap } from 'react-leaflet'
import { divIcon } from 'leaflet'

const CONF_COLORS = { HIGH: '#22c55e', MEDIUM: '#f59e0b', LOW: '#ef4444' }

function FlyToCluster({ clusterId, clusters }) {
  const map = useMap()
  useEffect(() => {
    if (!clusterId) return
    const c = clusters.find(cl => cl.id === clusterId)
    if (c) map.flyTo([c.lat, c.lon], 19, { duration: 0.7 })
  }, [clusterId, clusters, map])
  return null
}

function ClusterMarkers({ clusters, selected, onSelect }) {
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
          <strong>{c.count} deer</strong> · {c.confidence} · {c.label}
        </Tooltip>
      </Marker>
    )
  })
}

function Pass2WaypointMarkers({ waypoints }) {
  return waypoints.map(wp => {
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

function ObstacleOverlay({ obstacles }) {
  const powerPoints      = obstacles.filter(o => o.type === 'power_line').map(o => [o.lat, o.lon])
  const fencePosts       = obstacles.filter(o => o.type === 'fence_line')
  const towers           = obstacles.filter(o => o.type === 'tower')
  const guyWires         = obstacles.filter(o => o.type === 'guy_wire')
  const waterObs         = obstacles.filter(o => o.type === 'water')
  const vehicleObs       = obstacles.filter(o => o.type === 'vehicle')
  const antennaObs       = obstacles.filter(o => o.type === 'antenna')
  const pivotObs         = obstacles.filter(o => o.type === 'irrigation_pivot')
  const treeObs          = obstacles.filter(o => o.type === 'tree')
  const buildingObs      = obstacles.filter(o => o.type === 'building')

  const fenceIcon = useMemo(() => divIcon({
    html: `<div style="width:7px;height:7px;border-radius:50%;background:#f97316;border:1px solid rgba(249,115,22,0.5);box-shadow:0 0 6px #f97316aa"></div>`,
    className: '',
    iconSize: [7, 7],
    iconAnchor: [3.5, 3.5],
  }), [])

  const treeIcon = useMemo(() => divIcon({
    html: `<div style="width:8px;height:8px;border-radius:50%;background:#22c55e;border:1px solid rgba(34,197,94,0.5);box-shadow:0 0 5px #22c55e99"></div>`,
    className: '',
    iconSize: [8, 8],
    iconAnchor: [4, 4],
  }), [])

  const vehicleIcon = useMemo(() => divIcon({
    html: `<div style="width:10px;height:10px;background:#f59e0b;transform:rotate(45deg);border:1px solid rgba(245,158,11,0.6);box-shadow:0 0 6px #f59e0baa"></div>`,
    className: '',
    iconSize: [10, 10],
    iconAnchor: [5, 5],
  }), [])

  const buildingIcon = useMemo(() => divIcon({
    html: `<div style="width:9px;height:9px;background:#94a3b8;border-radius:1px;border:1px solid rgba(148,163,184,0.5);box-shadow:0 0 4px #94a3b866"></div>`,
    className: '',
    iconSize: [9, 9],
    iconAnchor: [4.5, 4.5],
  }), [])

  // Group guy_wire obstacles into consecutive pairs and connect them
  const guyWirePairs = []
  if (guyWires.length >= 2) {
    for (let i = 0; i + 1 < guyWires.length; i += 2) {
      guyWirePairs.push([guyWires[i], guyWires[i + 1]])
    }
    // If odd count, last one renders as a dot (handled below)
  }
  const guyWireOrphans = guyWires.length % 2 === 1 ? [guyWires[guyWires.length - 1]] : []

  return (
    <>
      {/* Power line */}
      {powerPoints.length > 1 && (
        <Polyline positions={powerPoints} pathOptions={{ color: '#ef4444', weight: 2, dashArray: '8 5', opacity: 0.7 }}>
          <Tooltip sticky opacity={1}>Power line corridor — OSM confirmed</Tooltip>
        </Polyline>
      )}

      {/* Fence posts */}
      {fencePosts.map(o => (
        <Marker key={o.id} position={[o.lat, o.lon]} icon={fenceIcon}>
          <Tooltip sticky opacity={1}>{o.note}</Tooltip>
        </Marker>
      ))}

      {/* Tower exclusion circles */}
      {towers.map(o => (
        <Circle key={o.id} center={[o.lat, o.lon]} radius={o.exclusion_radius_m}
          pathOptions={{ color: '#dc2626', fillColor: '#dc2626', fillOpacity: 0.08, weight: 1.5, dashArray: '5 4' }}>
          <Tooltip sticky opacity={1}><strong>HAZARD</strong> · {o.note} · {o.exclusion_radius_m}m exclusion</Tooltip>
        </Circle>
      ))}

      {/* Guy wire — dashed lines between pairs */}
      {guyWirePairs.map(([a, b], i) => (
        <Polyline key={`gw-pair-${i}`}
          positions={[[a.lat, a.lon], [b.lat, b.lon]]}
          pathOptions={{ color: '#b91c1c', weight: 1.2, dashArray: '4 4', opacity: 0.75 }}>
          <Tooltip sticky opacity={1}>Guy wire hazard · {a.note}</Tooltip>
        </Polyline>
      ))}
      {guyWireOrphans.map(o => (
        <Circle key={o.id} center={[o.lat, o.lon]} radius={5}
          pathOptions={{ color: '#b91c1c', fillColor: '#b91c1c', fillOpacity: 0.5, weight: 1 }}>
          <Tooltip sticky opacity={1}>Guy wire · {o.note}</Tooltip>
        </Circle>
      ))}

      {/* Water — filled sky-blue circles */}
      {waterObs.map(o => (
        <Circle key={o.id} center={[o.lat, o.lon]} radius={o.exclusion_radius_m || 15}
          pathOptions={{ color: '#0ea5e9', fillColor: '#0ea5e9', fillOpacity: 0.25, weight: 1.5 }}>
          <Tooltip sticky opacity={1}>Water / wet area · {o.note}</Tooltip>
        </Circle>
      ))}

      {/* Vehicle — amber diamond divIcon markers */}
      {vehicleObs.map(o => (
        <Marker key={o.id} position={[o.lat, o.lon]} icon={vehicleIcon}>
          <Tooltip sticky opacity={1}>Moving hazard — vehicle detected · {o.note}</Tooltip>
        </Marker>
      ))}

      {/* Antenna — small purple circles */}
      {antennaObs.map(o => (
        <Circle key={o.id} center={[o.lat, o.lon]} radius={o.exclusion_radius_m || 8}
          pathOptions={{ color: '#a855f7', fillColor: '#a855f7', fillOpacity: 0.15, weight: 1.5 }}>
          <Tooltip sticky opacity={1}>Antenna / comms mast · {o.note} · {o.height_m}m AGL</Tooltip>
        </Circle>
      ))}

      {/* Irrigation pivot — dashed lime circle at pivot radius */}
      {pivotObs.map(o => (
        <Circle key={o.id} center={[o.lat, o.lon]} radius={o.exclusion_radius_m || 50}
          pathOptions={{ color: '#84cc16', fillColor: '#84cc16', fillOpacity: 0.05, weight: 1.5, dashArray: '6 5' }}>
          <Tooltip sticky opacity={1}>Irrigation pivot · {o.exclusion_radius_m}m sweep radius · {o.note}</Tooltip>
        </Circle>
      ))}

      {/* Tree — small green dot markers (like fence posts) */}
      {treeObs.map(o => (
        <Marker key={o.id} position={[o.lat, o.lon]} icon={treeIcon}>
          <Tooltip sticky opacity={1}>Tree / canopy · {o.note}</Tooltip>
        </Marker>
      ))}

      {/* Building — slate square markers */}
      {buildingObs.map(o => (
        <Marker key={o.id} position={[o.lat, o.lon]} icon={buildingIcon}>
          <Tooltip sticky opacity={1}>Building footprint · {o.note}</Tooltip>
        </Marker>
      ))}
    </>
  )
}

function LakeOverlay({ lake }) {
  if (!lake) return null
  return (
    <Circle center={lake.center} radius={lake.radius_m}
      pathOptions={{ color: '#38bdf8', fillColor: '#0ea5e9', fillOpacity: 0.18, weight: 1 }}>
      <Tooltip opacity={1}>{lake.label}</Tooltip>
    </Circle>
  )
}

function PropertyBoundary({ bounds }) {
  const sw = [bounds.south, bounds.west]
  const ne = [bounds.north, bounds.east]
  return (
    <Rectangle bounds={[sw, ne]}
      pathOptions={{ color: '#475569', fillOpacity: 0, weight: 1.5, dashArray: '10 6' }} />
  )
}

export default function PropertyMap({ selectedCluster, onSelectCluster, waypoints, bounds, lake, clusters, obstacles }) {
  if (!bounds) return null
  return (
    <MapContainer
      center={bounds.center}
      zoom={17}
      style={{ flex: 1, width: '100%' }}
      zoomControl={true}
    >
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
        attribution="Tiles &copy; Esri"
        maxZoom={20}
      />
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png"
        attribution=""
        opacity={0.65}
      />
      <FlyToCluster clusterId={selectedCluster} clusters={clusters} />
      <PropertyBoundary bounds={bounds} />
      <LakeOverlay lake={lake} />
      <ObstacleOverlay obstacles={obstacles} />
      <Pass2WaypointMarkers waypoints={waypoints} />
      <ClusterMarkers clusters={clusters} selected={selectedCluster} onSelect={onSelectCluster} />
    </MapContainer>
  )
}
