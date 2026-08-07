import { useEffect, useState } from 'react'
import { api } from '../api'
import { Device } from '../types'

function percentage(specs: Record<string, unknown>, key: string, fallback: number) {
  const value = specs[key]
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.min(100, Math.round(value))) : fallback
}

export default function DeviceMonitor() {
  const [devices, setDevices] = useState<Device[]>([])

  useEffect(() => {
    const load = () => api.get<Device[]>('/devices').then(setDevices).catch(() => {})
    load()
    const timer = window.setInterval(load, 15000)
    return () => window.clearInterval(timer)
  }, [])

  return <section className="device-monitor" aria-label="Connected resource monitor">
    <div className="monitor-heading"><span className="monitor-pulse" /><div><strong>Connected resources</strong><small>{devices.filter((device) => device.online).length} workers online</small></div></div>
    <div className="monitor-device-list">
      {devices.slice(0, 4).map((device, index) => {
        const cpu = percentage(device.specs, 'cpu_percent', 0)
        const ram = percentage(device.specs, 'memory_percent', 0)
        return <div className="monitor-device" key={device.id}>
          <div className="monitor-device-name"><i className={device.online ? 'online' : ''} /><strong>{device.name}</strong><small>{device.online ? 'Online' : 'Offline'}</small></div>
          <div className="monitor-bars"><span><label>CPU {cpu}%</label><i><b style={{ width: `${cpu}%` }} /></i></span><span><label>RAM {ram}%</label><i><b style={{ width: `${ram}%` }} /></i></span></div>
        </div>
      })}
      {!devices.length && <div className="monitor-empty">No worker has been registered yet.</div>}
    </div>
    <div className="monitor-cloud"><span className="monitor-cloud-title">Cloud models</span>{['GPT API', 'Claude', 'Gemini'].map((model) => <span className="cloud-model" key={model}><i />{model}</span>)}</div>
  </section>
}
