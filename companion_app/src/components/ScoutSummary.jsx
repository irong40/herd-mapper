import { CheckCircle, AlertTriangle } from 'lucide-react'
import { PowerLineIcon, FenceIcon, TowerHazardIcon, WaypointIcon } from './icons'

const TYPE_ICONS = {
  power_line: (s) => <PowerLineIcon size={s} color="#ef4444" />,
  fence_line: (s) => <FenceIcon size={s} color="#f97316" />,
  tower:      (s) => <TowerHazardIcon size={s} color="#dc2626" />,
}

const TYPE_LABELS = {
  power_line: 'Power line',
  fence_line: 'Fence line',
  tower:      'Tower / structure',
}

export default function ScoutSummary({ obstacles, aglRange, obstacleSummary, pendingAlerts, scoutComplete }) {
  const summaryEntries = Object.entries(obstacleSummary ?? {})

  return (
    <div className="bg-[#0c0f16]/95 border-t border-slate-800/80 shrink-0" style={{ backdropFilter: 'blur(8px)' }}>
      <div className="px-3 pt-2 pb-1">
        <div className="flex items-center gap-2 mb-2">
          <WaypointIcon size={12} color="#f59e0b" />
          <p className="text-[9px] text-slate-600 font-mono uppercase tracking-widest">Obstacle Profile</p>
          <span className="font-mono text-[9px] text-slate-700 ml-auto">{obstacles.length} obstacles mapped</span>
        </div>

        <div className="flex gap-3 items-start">
          {/* Obstacle type breakdown */}
          <div className="flex gap-2 flex-wrap flex-1">
            {summaryEntries.map(([type, count]) => (
              <div key={type} className="flex items-center gap-1.5 rounded px-2.5 py-1.5 border border-slate-800/80 bg-slate-900/40">
                {TYPE_ICONS[type]?.(13) ?? <span className="w-3 h-3 rounded-full bg-slate-600" />}
                <span className="text-sm font-bold font-mono tabular-nums text-slate-300">{count}</span>
                <span className="text-[9px] text-slate-600 font-mono uppercase tracking-widest">{TYPE_LABELS[type] ?? type}</span>
              </div>
            ))}
          </div>

          {/* AGL range */}
          {aglRange && (
            <div className="flex-shrink-0 rounded px-3 py-1.5 border border-indigo-900/50 bg-indigo-950/20 text-center">
              <div className="text-[9px] text-slate-600 font-mono uppercase tracking-widest mb-0.5">Mission AGL range</div>
              <div className="text-sm font-bold font-mono text-indigo-300 tabular-nums">
                {aglRange.min_m}m – {aglRange.max_m}m
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="border-t border-slate-800/60 px-3 py-2">
        {scoutComplete ? (
          <div className="flex items-center justify-center gap-2 py-1.5 rounded border border-green-800/50 bg-green-950/20">
            <CheckCircle size={13} className="text-green-400" />
            <span className="text-[11px] text-green-400 font-mono uppercase tracking-widest">
              Profile saved · load census mission to apply AGL values
            </span>
          </div>
        ) : (
          <div className="flex items-center justify-center gap-2 py-1.5 rounded border border-amber-800/50 bg-amber-950/20">
            <AlertTriangle size={13} className="text-amber-400" />
            <span className="text-[11px] text-amber-400 font-mono uppercase tracking-widest">
              {pendingAlerts.length} alert{pendingAlerts.length !== 1 ? 's' : ''} pending · resolve to finalize profile
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
