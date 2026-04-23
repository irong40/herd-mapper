import { pass2Waypoints } from '../mockData'

const CONF_COLORS = { HIGH: 'text-green-400', MEDIUM: 'text-amber-400' }

export default function TargetQueue({ selectedCluster, onSelect }) {
  return (
    <div className="bg-slate-900 border-t border-slate-700 px-3 py-2 shrink-0">
      <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Pass 2 Target Queue</p>
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
                ? <span className="text-xs text-red-400">🔒 LOCKED</span>
                : <span className="text-xs text-green-400">✓ READY</span>
              }
            </div>
            <div className={`text-sm font-bold ${CONF_COLORS[wp.confidence]}`}>{wp.count} deer</div>
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
