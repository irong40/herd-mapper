import { ShieldCheck, ShieldX, CheckCircle, AlertTriangle } from 'lucide-react'
import { obstacles } from '../mockData'
import { PowerLineIcon, FenceIcon, TowerHazardIcon } from './icons'

const LOW_CONF = obstacles.filter(o => o.confidence === 'LOW')
const MED_CONF = obstacles.filter(o => o.confidence === 'MEDIUM')

function ObsIcon({ type, size = 15 }) {
  if (type === 'power_line') return <PowerLineIcon size={size} color="#ef4444" />
  if (type === 'fence_line') return <FenceIcon size={size} color="#f97316" />
  if (type === 'tower')      return <TowerHazardIcon size={size} color="#dc2626" />
  return null
}

function Alert({ obs, onResolve }) {
  return (
    <div className="rounded-lg mb-2 border border-red-900/60 bg-red-950/25 overflow-hidden">
      <div className="px-3 py-2.5">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[9px] font-bold font-mono tracking-widest px-1.5 py-0.5 rounded bg-red-700/80 text-red-200">LOW</span>
          <ObsIcon type={obs.type} size={13} />
          <span className="text-xs font-semibold text-slate-200 uppercase tracking-wide">
            {obs.type.replace('_', ' ')}
          </span>
        </div>
        <p className="text-[11px] text-slate-400 leading-relaxed mb-1">{obs.note}</p>
        <p className="text-[10px] text-slate-600 font-mono">
          HGT {obs.height_m}m &nbsp;·&nbsp; EXCL {obs.exclusion_radius_m}m
        </p>
      </div>
      <div className="flex border-t border-red-900/40">
        <button
          onClick={() => onResolve(obs.id, 'hazard')}
          className="flex-1 flex items-center justify-center gap-1.5 text-[11px] py-2 bg-red-900/30 hover:bg-red-800/50 text-red-300 font-medium transition-colors border-r border-red-900/40"
        >
          <ShieldX size={12} /> MARK HAZARD
        </button>
        <button
          onClick={() => onResolve(obs.id, 'safe')}
          className="flex-1 flex items-center justify-center gap-1.5 text-[11px] py-2 bg-slate-800/30 hover:bg-slate-700/40 text-slate-300 font-medium transition-colors"
        >
          <ShieldCheck size={12} /> CONFIRM SAFE
        </button>
      </div>
    </div>
  )
}

function ResolvedBadge({ resolution }) {
  if (resolution === 'safe') return (
    <div className="flex items-center gap-2 rounded px-3 py-2 mb-2 border border-green-900/40 bg-green-950/20">
      <ShieldCheck size={12} className="text-green-500" />
      <span className="text-[11px] text-green-500 font-mono">CONFIRMED SAFE — waypoint unlocked</span>
    </div>
  )
  return (
    <div className="flex items-center gap-2 rounded px-3 py-2 mb-2 border border-red-900/40 bg-red-950/20">
      <ShieldX size={12} className="text-red-500" />
      <span className="text-[11px] text-red-500 font-mono">MARKED HAZARD — route excluded</span>
    </div>
  )
}

export default function AlertPanel({ resolvedObstacles, onResolve }) {
  const pending    = LOW_CONF.filter(o => !resolvedObstacles[o.id])
  const resolved   = LOW_CONF.filter(o =>  resolvedObstacles[o.id])
  const softAlerts = MED_CONF.slice(0, 3)

  return (
    <div className="w-72 bg-[#0c0f16]/95 border-l border-slate-800/80 flex flex-col overflow-hidden" style={{ backdropFilter: 'blur(8px)' }}>

      <div className="px-4 py-2.5 border-b border-slate-800/80">
        <div className="flex items-center gap-2">
          {pending.length > 0 && <AlertTriangle size={13} className="text-red-400" />}
          <span className="text-xs font-semibold tracking-widest uppercase font-mono text-slate-300">
            Obstacle Alerts
          </span>
          {pending.length > 0 && (
            <span className="ml-auto text-[9px] font-mono font-bold bg-red-700/80 text-red-200 px-2 py-0.5 rounded">
              {pending.length} PENDING
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3">

        {pending.length === 0 && LOW_CONF.length > 0 && (
          <div className="flex items-center justify-center gap-2 text-green-400 text-[11px] py-4 font-mono">
            <CheckCircle size={13} /> ALL ALERTS RESOLVED
          </div>
        )}

        {pending.length > 0 && (
          <>
            <p className="text-[9px] text-slate-600 font-mono uppercase tracking-widest mb-2">Requires confirmation</p>
            {pending.map(o => <Alert key={o.id} obs={o} onResolve={onResolve} />)}
          </>
        )}

        {resolved.length > 0 && (
          <>
            <p className="text-[9px] text-slate-600 font-mono uppercase tracking-widest mt-2 mb-2">Resolved</p>
            {resolved.map(o => <ResolvedBadge key={o.id} resolution={resolvedObstacles[o.id]} />)}
          </>
        )}

        {softAlerts.length > 0 && (
          <>
            <p className="text-[9px] text-slate-600 font-mono uppercase tracking-widest mt-3 mb-2">Auto-classified</p>
            {softAlerts.map(o => (
              <div key={o.id} className="flex items-center gap-2 rounded px-2.5 py-2 mb-1 border border-slate-800/60 bg-slate-900/40">
                <span className="text-[9px] font-mono font-bold bg-amber-800/60 text-amber-300 px-1.5 py-0.5 rounded">MED</span>
                <ObsIcon type={o.type} size={12} />
                <span className="text-[11px] text-slate-400 font-mono">{o.type.replace('_', ' ')} · {o.height_m}m</span>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Legend */}
      <div className="px-3 py-2.5 border-t border-slate-800/80">
        <p className="text-[9px] text-slate-600 font-mono uppercase tracking-widest mb-2">Map Legend</p>
        <div className="space-y-1.5">
          <LegendRow icon={<PowerLineIcon size={13} color="#ef4444" />} label="Power line corridor" />
          <LegendRow icon={<FenceIcon size={13} color="#f97316" />} label="Fence line posts" />
          <LegendRow icon={<TowerHazardIcon size={13} color="#dc2626" />} label="Tower exclusion zone" />
          <LegendRow dot="#22c55e" label="HIGH confidence cluster" />
          <LegendRow dot="#f59e0b" label="MEDIUM confidence cluster" />
          <LegendRow dot="#818cf8" label="Pass 2 waypoint" />
        </div>
      </div>
    </div>
  )
}

function LegendRow({ icon, dot, label }) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-slate-500">
      {icon ?? <span className="w-2.5 h-2.5 rounded-full shrink-0 inline-block" style={{ background: dot }} />}
      {label}
    </div>
  )
}
