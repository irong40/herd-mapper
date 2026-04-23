import { pass2Waypoints } from '../mockData'
import { LockIcon, CheckReadyIcon, WaypointIcon, DeerClusterIcon } from './icons'

const CONF_COLORS = { HIGH: 'text-green-400', MEDIUM: 'text-amber-400' }
const DEER_COLORS = { HIGH: '#22c55e', MEDIUM: '#f59e0b' }

export default function TargetQueue({ selectedCluster, onSelect }) {
  return (
    <div className="bg-slate-900 border-t border-slate-700 px-3 py-2 shrink-0">
      <div className="flex items-center gap-2 mb-2">
        <WaypointIcon size={13} color="#818cf8" />
        <p className="text-xs text-slate-500 uppercase tracking-wide">Pass 2 Target Queue</p>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {pass2Waypoints.map(wp => (
          <button
            key={wp.id}
            onClick={() => !wp.locked && onSelect(wp.id)}
            className={`flex-shrink-0 rounded-lg px-3 py-2 border text-left transition-colors
              ${wp.locked
                ? 'border-red-800 bg-red-950/30 cursor-not-allowed opacity-70'
                : selectedCluster === wp.id
                  ? 'border-indigo-400 bg-indigo-900/40'
                  : 'border-slate-700 bg-slate-800 hover:border-slate-500'
              }`}
          >
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-xs font-bold text-slate-300">WP{wp.index}</span>
              {wp.locked
                ? <><LockIcon size={12} color="#f87171" /><span className="text-xs text-red-400">LOCKED</span></>
                : <><CheckReadyIcon size={12} color="#4ade80" /><span className="text-xs text-green-400">READY</span></>
              }
            </div>
            <div className="flex items-center gap-1.5">
              <DeerClusterIcon size={14} color={DEER_COLORS[wp.confidence]} />
              <span className={`text-sm font-bold ${CONF_COLORS[wp.confidence]}`}>{wp.count} deer</span>
            </div>
            <div className="text-xs text-slate-500">{wp.safe_alt_m}m AGL</div>
            {wp.locked && (
              <div className="text-xs text-red-400 mt-1 max-w-32 leading-tight">{wp.lock_reason}</div>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
