import { AlertTriangle } from 'lucide-react'
import { DroneIcon, DeerClusterIcon, WaypointIcon } from './icons'
import { clusters, pass2Waypoints, obstacles } from '../mockData'

const totalDeer = clusters.reduce((s, c) => s + c.count, 0)
const locked = pass2Waypoints.filter(w => w.locked).length
const pendingAlerts = obstacles.filter(o => o.confidence === 'LOW').length

export default function StatusBar() {
  return (
    <div className="h-12 bg-slate-900 border-b border-slate-700 flex items-center px-4 gap-6 shrink-0">
      <div className="flex items-center gap-2">
        <DroneIcon size={18} color="#22c55e" />
        <span className="text-sm font-semibold text-slate-100">Herd Mapper</span>
        <span className="text-xs text-slate-500 ml-1">DEMO — Pass 1 Complete</span>
      </div>

      <div className="h-4 w-px bg-slate-700" />

      <Stat label="Clusters" value={clusters.length} color="text-green-400" icon={<DeerClusterIcon size={14} color="#22c55e" />} />
      <Stat label="Animals" value={totalDeer} color="text-green-300" icon={<DeerClusterIcon size={14} color="#86efac" />} />
      <Stat label="Pass 2 WPs" value={pass2Waypoints.length} color="text-indigo-400" icon={<WaypointIcon size={14} color="#818cf8" />} />
      {locked > 0 && <Stat label="Locked" value={locked} color="text-red-400" />}
      {pendingAlerts > 0 && (
        <div className="ml-auto flex items-center gap-2 bg-red-900/40 border border-red-700 rounded px-3 py-1">
          <AlertTriangle size={13} className="text-red-400 animate-pulse" />
          <span className="text-xs text-red-300 font-medium">{pendingAlerts} alert{pendingAlerts > 1 ? 's' : ''} require operator review</span>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color, icon }) {
  return (
    <div className="flex items-center gap-1.5">
      {icon}
      <span className={`text-lg font-bold ${color}`}>{value}</span>
      <span className="text-xs text-slate-500">{label}</span>
    </div>
  )
}
