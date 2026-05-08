// Custom SVG icons for Herd Mapper — drone/wildlife census specific
// Generic UI icons come from lucide-react; these cover domain-specific shapes

export function DeerClusterIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Body */}
      <ellipse cx="12" cy="15" rx="4" ry="3" fill={color} opacity="0.9" />
      {/* Head */}
      <circle cx="12" cy="9.5" r="2.2" fill={color} />
      {/* Neck */}
      <rect x="11" y="11" width="2" height="2.5" fill={color} />
      {/* Antlers left */}
      <path d="M10.5 8 L8 5 M8 5 L7 3 M8 5 L6.5 6" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
      {/* Antlers right */}
      <path d="M13.5 8 L16 5 M16 5 L17 3 M16 5 L17.5 6" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
      {/* Legs */}
      <path d="M10 18 L9 22 M14 18 L15 22" stroke={color} strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}

export function ThermalBlobIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Heat signature blob */}
      <ellipse cx="12" cy="13" rx="5" ry="4" fill={color} opacity="0.85" />
      {/* Heat shimmer lines */}
      <path d="M9 8 Q9.5 6 9 4" stroke={color} strokeWidth="1.3" strokeLinecap="round" opacity="0.6" />
      <path d="M12 7 Q12.5 5 12 3" stroke={color} strokeWidth="1.3" strokeLinecap="round" opacity="0.8" />
      <path d="M15 8 Q15.5 6 15 4" stroke={color} strokeWidth="1.3" strokeLinecap="round" opacity="0.6" />
    </svg>
  )
}

export function TowerHazardIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Tower mast */}
      <line x1="12" y1="3" x2="12" y2="18" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      {/* Cross arms */}
      <line x1="7" y1="8" x2="17" y2="8" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="8.5" y1="13" x2="15.5" y2="13" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      {/* Base legs */}
      <path d="M12 18 L7 22 M12 18 L17 22" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      {/* Guy wires */}
      <path d="M7 8 L3 22" stroke={color} strokeWidth="0.8" strokeLinecap="round" opacity="0.5" />
      <path d="M17 8 L21 22" stroke={color} strokeWidth="0.8" strokeLinecap="round" opacity="0.5" />
      {/* Warning dot at top */}
      <circle cx="12" cy="2" r="1.5" fill={color} />
    </svg>
  )
}

export function PowerLineIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Poles */}
      <line x1="5" y1="5" x2="5" y2="18" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <line x1="19" y1="5" x2="19" y2="18" stroke={color} strokeWidth="2" strokeLinecap="round" />
      {/* Cross arms */}
      <line x1="2" y1="8" x2="8" y2="8" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="16" y1="8" x2="22" y2="8" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      {/* Catenary wire sag */}
      <path d="M3 9 Q12 14 21 9" stroke={color} strokeWidth="1.3" fill="none" strokeLinecap="round" />
    </svg>
  )
}

export function FenceIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Posts */}
      <line x1="4" y1="4" x2="4" y2="20" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <line x1="12" y1="4" x2="12" y2="20" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <line x1="20" y1="4" x2="20" y2="20" stroke={color} strokeWidth="2" strokeLinecap="round" />
      {/* Rails */}
      <line x1="2" y1="9" x2="22" y2="9" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="2" y1="15" x2="22" y2="15" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function WaypointIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Outer ring */}
      <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.5" />
      {/* Cross hairs */}
      <line x1="12" y1="3" x2="12" y2="7" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="17" x2="12" y2="21" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="3" y1="12" x2="7" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="17" y1="12" x2="21" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      {/* Center dot */}
      <circle cx="12" cy="12" r="2" fill={color} />
    </svg>
  )
}

export function DroneIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Arms */}
      <line x1="4" y1="4" x2="9" y2="9" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="20" y1="4" x2="15" y2="9" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="4" y1="20" x2="9" y2="15" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="20" y1="20" x2="15" y2="15" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      {/* Motor hubs */}
      <circle cx="4" cy="4" r="2" fill={color} opacity="0.7" />
      <circle cx="20" cy="4" r="2" fill={color} opacity="0.7" />
      <circle cx="4" cy="20" r="2" fill={color} opacity="0.7" />
      <circle cx="20" cy="20" r="2" fill={color} opacity="0.7" />
      {/* Body */}
      <rect x="9" y="9" width="6" height="6" rx="1.5" fill={color} />
      {/* Camera gimbal */}
      <circle cx="12" cy="15" r="1.5" stroke={color} strokeWidth="1" fill="none" />
    </svg>
  )
}

export function LockIcon({ size = 16, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="5" y="11" width="14" height="10" rx="2" stroke={color} strokeWidth="1.8" fill={color} fillOpacity="0.2" />
      <path d="M8 11V7a4 4 0 018 0v4" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="16" r="1.5" fill={color} />
    </svg>
  )
}

export function CheckReadyIcon({ size = 16, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.8" />
      <path d="M7.5 12 L10.5 15 L16.5 9" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// --- Obstacle class icons added for 10-type Cowan system ---

export function GuyWireIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Anchor point at top-center */}
      <circle cx="12" cy="5" r="1.5" fill={color} opacity="0.9" />
      {/* Left guy wire — angled down-left, dashed */}
      <line x1="12" y1="5" x2="4" y2="20"
        stroke={color} strokeWidth="1.2" strokeLinecap="round"
        strokeDasharray="2.5 2" />
      {/* Right guy wire — angled down-right, dashed */}
      <line x1="12" y1="5" x2="20" y2="20"
        stroke={color} strokeWidth="1.2" strokeLinecap="round"
        strokeDasharray="2.5 2" />
      {/* Ground anchors */}
      <line x1="2" y1="20" x2="6" y2="20" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="18" y1="20" x2="22" y2="20" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

export function WaterIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* First wave */}
      <path d="M3 11 Q6 8 9 11 Q12 14 15 11 Q18 8 21 11"
        stroke={color} strokeWidth="1.6" strokeLinecap="round" fill="none" />
      {/* Second wave */}
      <path d="M3 16 Q6 13 9 16 Q12 19 15 16 Q18 13 21 16"
        stroke={color} strokeWidth="1.6" strokeLinecap="round" fill="none" />
    </svg>
  )
}

export function VehicleIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Vehicle body — rounded rect, top-down */}
      <rect x="7" y="5" width="10" height="14" rx="2.5"
        stroke={color} strokeWidth="1.6" fill={color} fillOpacity="0.15" />
      {/* Wheels — 4 corners */}
      <rect x="4" y="6" width="3" height="4" rx="1" fill={color} opacity="0.8" />
      <rect x="17" y="6" width="3" height="4" rx="1" fill={color} opacity="0.8" />
      <rect x="4" y="14" width="3" height="4" rx="1" fill={color} opacity="0.8" />
      <rect x="17" y="14" width="3" height="4" rx="1" fill={color} opacity="0.8" />
      {/* Windshield line */}
      <line x1="8" y1="8" x2="16" y2="8" stroke={color} strokeWidth="1" strokeLinecap="round" opacity="0.6" />
    </svg>
  )
}

export function AntennaIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Mast */}
      <line x1="12" y1="3" x2="12" y2="20" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      {/* Signal arcs — one side */}
      <path d="M15 8 Q18 10.5 15 13" stroke={color} strokeWidth="1.3" strokeLinecap="round" fill="none" opacity="0.9" />
      <path d="M16.5 5.5 Q21 9 16.5 14.5" stroke={color} strokeWidth="1.1" strokeLinecap="round" fill="none" opacity="0.55" />
      {/* Base */}
      <line x1="9" y1="20" x2="15" y2="20" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function IrrigationPivotIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Center pivot point */}
      <circle cx="6" cy="12" r="2" fill={color} opacity="0.9" />
      {/* Pivot arm — horizontal extending right */}
      <line x1="6" y1="12" x2="21" y2="12" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      {/* Wheel towers under the arm */}
      <line x1="11" y1="12" x2="11" y2="16" stroke={color} strokeWidth="1.2" strokeLinecap="round" opacity="0.7" />
      <line x1="16" y1="12" x2="16" y2="16" stroke={color} strokeWidth="1.2" strokeLinecap="round" opacity="0.7" />
      {/* Wheel dots */}
      <circle cx="11" cy="17" r="1.2" fill={color} opacity="0.7" />
      <circle cx="16" cy="17" r="1.2" fill={color} opacity="0.7" />
      {/* Arc suggestion — dashed quarter arc */}
      <path d="M6 3 Q21 3 21 12" stroke={color} strokeWidth="1" strokeLinecap="round"
        fill="none" strokeDasharray="2.5 2" opacity="0.5" />
    </svg>
  )
}

export function TreeIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Top-down canopy circle */}
      <circle cx="12" cy="12" r="8" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.2" />
      {/* Cross — trunk/branching from above */}
      <line x1="12" y1="5" x2="12" y2="19" stroke={color} strokeWidth="1.2" strokeLinecap="round" opacity="0.8" />
      <line x1="5" y1="12" x2="19" y2="12" stroke={color} strokeWidth="1.2" strokeLinecap="round" opacity="0.8" />
    </svg>
  )
}

export function BuildingIcon({ size = 20, color = 'currentColor', className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      {/* Building footprint — rectangle, top-down */}
      <rect x="4" y="5" width="16" height="14" rx="1"
        stroke={color} strokeWidth="1.6" fill={color} fillOpacity="0.18" />
      {/* X cross — top-down structural marker */}
      <line x1="4" y1="5" x2="20" y2="19" stroke={color} strokeWidth="1" strokeLinecap="round" opacity="0.5" />
      <line x1="20" y1="5" x2="4" y2="19" stroke={color} strokeWidth="1" strokeLinecap="round" opacity="0.5" />
    </svg>
  )
}
