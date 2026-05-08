// Inline mock data — mirrors what core/mock_data.py generates
// When real hardware arrives, App.jsx fetches from the Python pipeline output instead

export const bounds = {
  center: [36.7821, -76.4523],
  north: 36.7841, south: 36.7801,
  east: -76.4491, west: -76.4555,
  name: 'Demo Property — 50 acres',
}

export const lake = {
  center: [36.7812, -76.4537],
  radius_m: 45,
  label: 'Pond',
}

export const clusters = [
  { id: 'cluster_001', lat: 36.7813, lon: -76.4531, count: 8, confidence: 'HIGH',   label: 'Herd near pond edge' },
  { id: 'cluster_002', lat: 36.7809, lon: -76.4539, count: 7, confidence: 'HIGH',   label: 'Bedded group — pond NW' },
  { id: 'cluster_003', lat: 36.7820, lon: -76.4515, count: 3, confidence: 'MEDIUM', label: 'Possible deer — field center' },
  { id: 'cluster_004', lat: 36.7828, lon: -76.4504, count: 2, confidence: 'MEDIUM', label: 'Unverified — tree line edge' },
]

export const obstacles = [
  // Power line corridor — diagonal
  { id: 'power_001', lat: 36.7841, lon: -76.4555, height_m: 14, type: 'power_line', confidence: 'HIGH',   exclusion_radius_m: 8,  note: 'OSM confirmed — utility corridor' },
  { id: 'power_002', lat: 36.7831, lon: -76.4539, height_m: 14, type: 'power_line', confidence: 'HIGH',   exclusion_radius_m: 8,  note: 'OSM confirmed — utility corridor' },
  { id: 'power_003', lat: 36.7821, lon: -76.4523, height_m: 14, type: 'power_line', confidence: 'HIGH',   exclusion_radius_m: 8,  note: 'OSM confirmed — utility corridor' },
  { id: 'power_004', lat: 36.7811, lon: -76.4507, height_m: 14, type: 'power_line', confidence: 'HIGH',   exclusion_radius_m: 8,  note: 'OSM confirmed — utility corridor' },
  { id: 'power_005', lat: 36.7801, lon: -76.4491, height_m: 14, type: 'power_line', confidence: 'HIGH',   exclusion_radius_m: 8,  note: 'OSM confirmed — utility corridor' },
  // Fence north boundary (sampled posts)
  { id: 'fence_n_1', lat: 36.7840, lon: -76.4545, height_m: 6,  type: 'fence_line', confidence: 'MEDIUM', exclusion_radius_m: 4,  note: 'Post pattern inferred — north boundary' },
  { id: 'fence_n_2', lat: 36.7840, lon: -76.4530, height_m: 6,  type: 'fence_line', confidence: 'MEDIUM', exclusion_radius_m: 4,  note: 'Post pattern inferred — north boundary' },
  { id: 'fence_n_3', lat: 36.7840, lon: -76.4515, height_m: 6,  type: 'fence_line', confidence: 'MEDIUM', exclusion_radius_m: 4,  note: 'Post pattern inferred — north boundary' },
  { id: 'fence_n_4', lat: 36.7840, lon: -76.4500, height_m: 6,  type: 'fence_line', confidence: 'MEDIUM', exclusion_radius_m: 4,  note: 'Post pattern inferred — north boundary' },
  // Tower NE corner — LOW confidence, guy wire hazard
  { id: 'tower_001', lat: 36.7836, lon: -76.4499, height_m: 28, type: 'tower',      confidence: 'LOW',    exclusion_radius_m: 42, note: 'Unidentified structure — possible comms tower. GUY WIRE HAZARD. Operator confirm required.' },
  // Guy wires anchored near tower base — pair renders as a dashed line
  { id: 'guywire_001', lat: 36.7834, lon: -76.4496, height_m: 2,  type: 'guy_wire', confidence: 'LOW',    exclusion_radius_m: 5,  note: 'Guy wire anchor NE — tower_001' },
  { id: 'guywire_002', lat: 36.7838, lon: -76.4502, height_m: 2,  type: 'guy_wire', confidence: 'LOW',    exclusion_radius_m: 5,  note: 'Guy wire anchor NW — tower_001' },
  // Water — pond edge / drainage low spot west side
  { id: 'water_001',   lat: 36.7817, lon: -76.4542, height_m: 0,  type: 'water',    confidence: 'HIGH',   exclusion_radius_m: 18, note: 'Drainage pond edge — soft ground, avoid low approaches' },
  // Vehicle — near south entrance
  { id: 'vehicle_001', lat: 36.7803, lon: -76.4519, height_m: 2,  type: 'vehicle',  confidence: 'MEDIUM', exclusion_radius_m: 6,  note: 'Parked vehicle detected near south gate' },
  // Antenna — north boundary
  { id: 'antenna_001', lat: 36.7839, lon: -76.4521, height_m: 18, type: 'antenna',  confidence: 'MEDIUM', exclusion_radius_m: 12, note: 'Wireless repeater — confirmed OSM' },
  // Irrigation pivot — mid-property, 60m sweep radius
  { id: 'pivot_001',   lat: 36.7822, lon: -76.4508, height_m: 3,  type: 'irrigation_pivot', confidence: 'HIGH', exclusion_radius_m: 60, note: 'Center pivot irrigation — active season, rotor arm at 3m AGL' },
  // Treeline — east edge
  { id: 'tree_001',    lat: 36.7830, lon: -76.4493, height_m: 12, type: 'tree',     confidence: 'HIGH',   exclusion_radius_m: 6,  note: 'Hardwood canopy — east treeline' },
  { id: 'tree_002',    lat: 36.7824, lon: -76.4495, height_m: 10, type: 'tree',     confidence: 'HIGH',   exclusion_radius_m: 5,  note: 'Hardwood canopy — east treeline' },
  // Building — south boundary near entrance
  { id: 'bldg_001',    lat: 36.7802, lon: -76.4526, height_m: 6,  type: 'building', confidence: 'HIGH',   exclusion_radius_m: 10, note: 'Outbuilding / storage structure — south boundary' },
]

// Base Pass 2 waypoints — locked state is derived reactively in App.jsx
export const pass2WaypointsBase = clusters.map((c, i) => {
  const nearTower = c.id === 'cluster_004'
  return {
    index: i + 1,
    ...c,
    id: c.id,
    safe_alt_m: nearTower ? 55 : 30,
    locked: nearTower,
    locked_by: nearTower ? 'tower_001' : null,
    lock_reason: nearTower ? 'Tower exclusion zone overlap — confirm obstacle before routing' : null,
  }
})
