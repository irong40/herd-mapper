import { useState } from 'react'
import PropertyMap from './components/PropertyMap'
import AlertPanel from './components/AlertPanel'
import StatusBar from './components/StatusBar'
import TargetQueue from './components/TargetQueue'

export default function App() {
  const [selectedCluster, setSelectedCluster] = useState(null)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw' }}>
      <StatusBar />
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <PropertyMap
            selectedCluster={selectedCluster}
            onSelectCluster={setSelectedCluster}
          />
          <TargetQueue
            selectedCluster={selectedCluster}
            onSelect={setSelectedCluster}
          />
        </div>
        <AlertPanel />
      </div>
    </div>
  )
}
