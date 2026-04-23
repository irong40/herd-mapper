import { pass2Waypoints } from '../mockData'
import { LockIcon, CheckReadyIcon, WaypointIcon, DeerClusterIcon } from './icons'

const CONF_COLORS  = { HIGH: 'text-green-400',  MEDIUM: 'text-amber-400' }
const DEER_COLORS  = { HIGH: '#22c55e',          MEDIUM: '#f59e0b' }

export default function TargetQueue({ selectedCluster, onSelect }) {
  return (
    <div className="bg-[#0c0f16]/95 border-t border-slate-800/80 px-3 py-2 shrink-0" style={{ backdropFilter: 'blur(8px)' }}>
      <div className="flex items-center gap-2 mb-2">
        <WaypointIcon size={12} color="#818cf8" />
        <p className="text-[9px] text-slate-600 font-mono uppercase tracking-widest">Pass 2 Target Queue</p>
        <span className="font-mono text-[9px] text-slate-700 ml-auto">{pass2Waypoints.length} waypoints</span>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {pass2Waypoints.map(wp => (
          <button
            key={wp.id}
            onClick={() => !wp.locked && onSelect(wp.id)}
            className={`flex-shrink-0 rounded-md px-3 py-2 border text-left transition-all
              ${wp.locked
                ? 'border-red-900/50 bg-red-950/20 cursor-not-allowed opacity-60'
                : selectedCluster === wp.id
                  ? 'border-indigo-500/60 bg-indigo-950/40 shadow-[0_0_12px_rgba(129,140,248,0.15)]'
                  : 'border-slate-800/80 bg-slate-900/40 hover:border-slate-700/80 hover:bg-slate-800/40'
              }`}
          >
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-[11px] font-bold font-mono text-slate-400">WP{wp.index}</span>
              {wp.locked
                ? <><LockIcon size={11} color="#f87171" /><span className="text-[9px] text-red-400 font-mono">LOCKED</span></>
                : <><CheckReadyIcon size={11} color="#4ade80" /><span className="text-[9px] text-green-500 font-mono">READY</span></>
              }
            </div>

            <div className="flex items-center gap-1.5 mb-0.5">
              <DeerClusterIcon size={13} color={DEER_COLORS[wp.confidence]} />
              <span className={`text-sm font-bold font-mono tabular-nums ${CONF_COLORS[wp.confidence]}`}>
                {wp.count}
              </span>
              <span className="text-[9px] text-slate-600 font-mono">deer</span>
            </div>

            <div className="text-[10px] text-slate-600 font-mono">{wp.safe_alt_m}m AGL</div>

            {wp.locked && (
              <div className="text-[9px] text-red-500/80 mt-1 max-w-28 leading-tight font-mono">{wp.lock_reason}</div>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
