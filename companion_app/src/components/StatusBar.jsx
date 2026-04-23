import { AlertTriangle } from 'lucide-react'
import { DroneIcon, DeerClusterIcon, WaypointIcon } from './icons'
import { clusters, pass2Waypoints, obstacles } from '../mockData'

const totalDeer = clusters.reduce((s, c) => s + c.count, 0)
const locked = pass2Waypoints.filter(w => w.locked).length
const pendingAlerts = obstacles.filter(o => o.confidence === 'LOW').length

export default function StatusBar() {
  return (
    <div className="h-11 bg-[#0a0d12]/95 border-b border-slate-800 flex items-center px-4 gap-5 shrink-0" style={{ backdropFilter: 'blur(8px)' }}>
      <div className="flex items-center gap-2">
        <DroneIcon size={16} color="#22c55e" />
        <span className="text-sm font-semibold tracking-wide text-slate-100">HERD MAPPER</span>
        <span className="text-[10px] text-slate-600 font-mono ml-1 uppercase tracking-widest">PASS 1 COMPLETE</span>
      </div>

      <div className="h-3 w-px bg-slate-800" />

      <Stat label="CLUSTERS" value={clusters.length} color="text-green-400" icon={<DeerClusterIcon size={13} color="#22c55e" />} />
      <Stat label="ANIMALS"  value={totalDeer}       color="text-green-300" icon={<DeerClusterIcon size={13} color="#86efac" />} />
      <Stat label="WPs"      value={pass2Waypoints.length} color="text-indigo-400" icon={<WaypointIcon size={13} color="#818cf8" />} />
      {locked > 0 && <Stat label="LOCKED" value={locked} color="text-red-400" />}

      {pendingAlerts > 0 && (
        <div className="ml-auto flex items-center gap-2 rounded px-3 py-1 border border-red-900/70 bg-red-950/40">
          <AlertTriangle size={12} className="text-red-400" />
          <span className="text-[11px] text-red-300 font-mono uppercase tracking-wide">
            {pendingAlerts} alert{pendingAlerts > 1 ? 's' : ''} · operator review required
          </span>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color, icon }) {
  return (
    <div className="flex items-center gap-1.5">
      {icon}
      <span className={`text-base font-bold font-mono tabular-nums ${color}`}>{value}</span>
      <span className="text-[9px] text-slate-600 font-mono uppercase tracking-widest">{label}</span>
    </div>
  )
}
