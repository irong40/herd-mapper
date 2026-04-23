import { AlertTriangle } from 'lucide-react'
import { DroneIcon, DeerClusterIcon, WaypointIcon } from './icons'
import { clusters } from '../mockData'

const totalDeer = clusters.reduce((s, c) => s + c.count, 0)

export default function StatusBar({ waypoints, pendingAlerts, pass2Ready, launchState, isLive, missionId }) {
  return (
    <div className="h-11 bg-[#0a0d12]/95 border-b border-slate-800 flex items-center px-4 gap-5 shrink-0" style={{ backdropFilter: 'blur(8px)' }}>
      <div className="flex items-center gap-2">
        <DroneIcon size={16} color={launchState === 'executing' ? '#f59e0b' : '#22c55e'} />
        <span className="text-sm font-semibold tracking-wide text-slate-100">HERD MAPPER</span>
        <span className="text-[10px] text-slate-600 font-mono ml-1 uppercase tracking-widest">
          {launchState === 'executing' ? 'PASS 2 — EXECUTING' : launchState === 'complete' ? 'PASS 2 — COMPLETE' : 'PASS 1 COMPLETE'}
        </span>
        {isLive
          ? <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-green-800/60 text-green-500 uppercase tracking-widest">LIVE · {missionId}</span>
          : <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-slate-700/60 text-slate-600 uppercase tracking-widest">DEMO</span>
        }
      </div>

      <div className="h-3 w-px bg-slate-800" />

      <Stat label="CLUSTERS" value={clusters.length} color="text-green-400" icon={<DeerClusterIcon size={13} color="#22c55e" />} />
      <Stat label="ANIMALS"  value={totalDeer}        color="text-green-300" icon={<DeerClusterIcon size={13} color="#86efac" />} />
      <Stat label="WPs"      value={waypoints.length} color="text-indigo-400" icon={<WaypointIcon size={13} color="#818cf8" />} />
      {waypoints.filter(w => w.locked).length > 0 && (
        <Stat label="LOCKED" value={waypoints.filter(w => w.locked).length} color="text-red-400" />
      )}

      {pendingAlerts.length > 0 && (
        <div className="ml-auto flex items-center gap-2 rounded px-3 py-1 border border-red-900/70 bg-red-950/40">
          <AlertTriangle size={12} className="text-red-400" />
          <span className="text-[11px] text-red-300 font-mono uppercase tracking-wide">
            {pendingAlerts.length} alert{pendingAlerts.length > 1 ? 's' : ''} · operator review required
          </span>
        </div>
      )}

      {pass2Ready && !launchState && (
        <div className="ml-auto flex items-center gap-2 rounded px-3 py-1 border border-green-800/60 bg-green-950/30">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse inline-block" />
          <span className="text-[11px] text-green-400 font-mono uppercase tracking-wide">
            Pass 2 ready · {waypoints.filter(w => !w.locked).length} waypoints queued
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
