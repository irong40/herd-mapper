import { useState } from 'react'
import { obstacles } from '../mockData'

const LOW_CONF = obstacles.filter(o => o.confidence === 'LOW')
const MED_CONF = obstacles.filter(o => o.confidence === 'MEDIUM')

const OBS_ICON = { power_line: '⚡', fence_line: '🚧', tower: '📡' }

function Alert({ obs, onResolve }) {
  const isLow = obs.confidence === 'LOW'
  return (
    <div className={`rounded-lg p-3 mb-2 border ${isLow ? 'border-red-500 bg-red-950/40' : 'border-amber-500 bg-amber-950/30'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs font-bold px-2 py-0.5 rounded ${isLow ? 'bg-red-600 text-white' : 'bg-amber-600 text-white'}`}>
              {obs.confidence}
            </span>
            <span className="text-sm font-medium text-slate-200">
              {OBS_ICON[obs.type]} {obs.type.replace('_', ' ').toUpperCase()}
            </span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">{obs.note}</p>
          <p className="text-xs text-slate-500 mt-1">Height: {obs.height_m}m · Exclusion: {obs.exclusion_radius_m}m radius</p>
        </div>
      </div>
      {isLow && (
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => onResolve(obs.id, 'hazard')}
            className="flex-1 text-xs py-1.5 rounded bg-red-700 hover:bg-red-600 text-white font-medium transition-colors"
          >
            Mark Hazard
          </button>
          <button
            onClick={() => onResolve(obs.id, 'safe')}
            className="flex-1 text-xs py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-white font-medium transition-colors"
          >
            Confirm Safe
          </button>
        </div>
      )}
    </div>
  )
}

export default function AlertPanel({ onObstacleResolved }) {
  const [resolved, setResolved] = useState({})

  const pending = LOW_CONF.filter(o => !resolved[o.id])
  const softAlerts = MED_CONF.slice(0, 3)

  function handleResolve(id, decision) {
    setResolved(r => ({ ...r, [id]: decision }))
    onObstacleResolved?.(id, decision)
    // In production: send decision back to Manifold 3 / update obstacle map
  }

  return (
    <div className="w-80 bg-slate-900 border-l border-slate-700 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700">
        <div className="flex items-center gap-2">
          {pending.length > 0 && (
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
          )}
          <span className="font-semibold text-sm text-slate-100">Obstacle Alerts</span>
          {pending.length > 0 && (
            <span className="ml-auto text-xs bg-red-600 text-white px-2 py-0.5 rounded-full font-bold">
              {pending.length} pending
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {pending.length === 0 && LOW_CONF.length > 0 ? (
          <div className="text-center text-green-400 text-sm py-4">
            All alerts resolved — Pass 2 ready
          </div>
        ) : null}

        {pending.length > 0 && (
          <>
            <p className="text-xs text-slate-500 mb-2 uppercase tracking-wide">Requires confirmation</p>
            {pending.map(o => <Alert key={o.id} obs={o} onResolve={handleResolve} />)}
          </>
        )}

        {softAlerts.length > 0 && (
          <>
            <p className="text-xs text-slate-500 mt-3 mb-2 uppercase tracking-wide">Auto-classified</p>
            {softAlerts.map(o => (
              <div key={o.id} className="rounded-lg p-2.5 mb-1.5 border border-slate-700 bg-slate-800/50">
                <div className="flex items-center gap-2">
                  <span className="text-xs bg-amber-700 text-white px-1.5 py-0.5 rounded">MED</span>
                  <span className="text-xs text-slate-300">{OBS_ICON[o.type]} {o.type.replace('_', ' ')} — {o.height_m}m</span>
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Legend */}
      <div className="px-3 py-2 border-t border-slate-700 space-y-1">
        <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Map Legend</p>
        <div className="flex items-center gap-2 text-xs text-slate-400"><span className="w-3 h-0.5 bg-red-500 inline-block" style={{borderTop:'2px dashed #ef4444'}}></span>Power line</div>
        <div className="flex items-center gap-2 text-xs text-slate-400"><span className="w-2.5 h-2.5 rounded-full bg-orange-500 inline-block"></span>Fence posts</div>
        <div className="flex items-center gap-2 text-xs text-slate-400"><span className="w-2.5 h-2.5 rounded-full border-2 border-red-600 inline-block"></span>Tower exclusion</div>
        <div className="flex items-center gap-2 text-xs text-slate-400"><span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block"></span>HIGH conf cluster</div>
        <div className="flex items-center gap-2 text-xs text-slate-400"><span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block"></span>MEDIUM conf cluster</div>
        <div className="flex items-center gap-2 text-xs text-slate-400"><span className="w-2.5 h-2.5 rounded-full bg-indigo-400 inline-block"></span>Pass 2 waypoint</div>
      </div>
    </div>
  )
}
