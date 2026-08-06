import { FormEvent, useEffect, useState } from 'react'
import { api, getDeviceDirectories } from '../api'
import { Device, SharedDirectory } from '../types'

const emptyDirectory = { alias: '', local_path: '', permission: 'read' as const }

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [directories, setDirectories] = useState<SharedDirectory[]>([])
  const [name, setName] = useState('')
  const [maxCpu, setMaxCpu] = useState('')
  const [maxGpu, setMaxGpu] = useState('')
  const [directoryForm, setDirectoryForm] = useState(emptyDirectory)
  const [editingDirectoryId, setEditingDirectoryId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const selected = devices.find((device) => device.id === selectedId) ?? null

  async function load() {
    try { setDevices(await api.get<Device[]>('/devices')) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '조회 실패') }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  async function selectDevice(device: Device) {
    setSelectedId(device.id)
    setName(device.name)
    setMaxCpu(device.resource_limits.max_cpu_percent?.toString() ?? '')
    setMaxGpu(device.resource_limits.max_gpu_percent?.toString() ?? '')
    setDirectoryForm(emptyDirectory)
    setEditingDirectoryId(null)
    setError('')
    try { setDirectories(await getDeviceDirectories(device.id)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '디렉터리 조회 실패') }
  }

  async function saveDevice(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    try {
      await api.patch<Device>(`/devices/${selected.id}`, {
        name,
        resource_limits: {
          max_cpu_percent: maxCpu ? Number(maxCpu) : null,
          max_gpu_percent: maxGpu ? Number(maxGpu) : null,
        },
      })
      await load()
      setMessage('Worker 설정을 저장했습니다.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '저장 실패') }
  }

  async function saveDirectory(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    try {
      if (editingDirectoryId) {
        await api.patch(`/devices/${selected.id}/directories/${editingDirectoryId}`, directoryForm)
      } else {
        await api.post(`/devices/${selected.id}/directories`, directoryForm)
      }
      setDirectories(await getDeviceDirectories(selected.id))
      setDirectoryForm(emptyDirectory)
      setEditingDirectoryId(null)
      setMessage('공유 디렉터리를 저장했습니다.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '디렉터리 저장 실패') }
  }

  async function deactivateDirectory(directoryId: number) {
    if (!selected || !confirm('이 디렉터리를 비활성화할까요?')) return
    try {
      await api.delete(`/devices/${selected.id}/directories/${directoryId}`)
      setDirectories(await getDeviceDirectories(selected.id))
    } catch (cause) { setError(cause instanceof Error ? cause.message : '디렉터리 변경 실패') }
  }

  async function removeDevice(deviceId: number) {
    if (!confirm('이 Worker를 삭제할까요?')) return
    await api.delete(`/devices/${deviceId}`)
    if (selectedId === deviceId) setSelectedId(null)
    load()
  }

  return <div>
    <h1>기기 관리</h1>
    <p className="subtitle">Worker의 이름, 새 작업 수용 기준과 공유 디렉터리를 관리합니다.</p>
    {error && <div className="error">{error}</div>}
    {message && <div style={{ color: 'var(--success)', marginBottom: 10 }}>{message}</div>}
    <div className="card">
      <table><thead><tr><th>이름</th><th>사양</th><th>상태</th><th></th></tr></thead><tbody>
        {devices.map((device) => <tr key={device.id} className={selectedId === device.id ? 'selected-row' : ''}>
          <td><strong>{device.name}</strong></td>
          <td style={{ fontSize: 13, color: 'var(--muted)' }}>{String(device.specs.os ?? '')} · CPU {String(device.specs.cpu_count ?? '?')}코어 · RAM {String(device.specs.ram_gb ?? '?')}GB {device.specs.cpu_percent != null && ` · 사용률 ${device.specs.cpu_percent}%`}</td>
          <td><span className={`badge ${device.online ? 'online' : 'offline'}`}>{device.online ? '온라인' : '오프라인'}</span></td>
          <td className="row"><button className="btn sm ghost" onClick={() => selectDevice(device)}>설정</button><button className="btn sm danger" onClick={() => removeDevice(device.id)}>삭제</button></td>
        </tr>)}
        {!devices.length && <tr><td colSpan={4} style={{ color: 'var(--muted)' }}>등록된 Worker가 없습니다.</td></tr>}
      </tbody></table>
    </div>

    {selected && <div className="device-editor">
      <section className="card"><h2>{selected.name} 설정</h2>
        <form onSubmit={saveDevice}>
          <label>Worker 이름</label><input value={name} onChange={(event) => setName(event.target.value)} required />
          <div className="resource-limit-grid">
            <div><label>CPU 수용 상한 (%)</label><input type="number" min="1" max="100" placeholder="제한 없음" value={maxCpu} onChange={(event) => setMaxCpu(event.target.value)} /></div>
            <div><label>GPU 수용 상한 (%)</label><input type="number" min="1" max="100" placeholder="제한 없음" value={maxGpu} onChange={(event) => setMaxGpu(event.target.value)} /></div>
          </div>
          <p className="muted">현재 사용률이 상한 이상이면 이 Worker에는 새 작업을 배정하지 않습니다. 실행 중인 Ollama 프로세스를 강제로 제한하는 값은 아닙니다.</p>
          <button className="btn">Worker 설정 저장</button>
        </form>
      </section>
      <section className="card"><h2>공유 디렉터리</h2>
        <p className="muted">모든 Worker 컨테이너에서 같은 절대 경로로 마운트된 경로를 등록하세요.</p>
        <form onSubmit={saveDirectory} className="directory-form">
          <input placeholder="별명 (예: 프로젝트 자료)" value={directoryForm.alias} onChange={(event) => setDirectoryForm({ ...directoryForm, alias: event.target.value })} required />
          <input placeholder="/shared/project" value={directoryForm.local_path} onChange={(event) => setDirectoryForm({ ...directoryForm, local_path: event.target.value })} required />
          <span className="directory-permission">읽기 전용</span>
          <button className="btn">{editingDirectoryId ? '수정 저장' : '디렉터리 추가'}</button>
          {editingDirectoryId && <button type="button" className="btn ghost" onClick={() => { setEditingDirectoryId(null); setDirectoryForm(emptyDirectory) }}>취소</button>}
        </form>
        <div className="directory-list">
          {directories.map((directory) => <div className="directory-row" key={directory.id}><div><strong>{directory.alias}</strong><small>{directory.local_path} · 읽기 전용 · {directory.is_active ? '활성' : '비활성'}</small></div><div className="row"><button className="btn sm ghost" onClick={() => { setEditingDirectoryId(directory.id); setDirectoryForm({ alias: directory.alias, local_path: directory.local_path, permission: 'read' }) }}>수정</button>{directory.is_active && <button className="btn sm danger" onClick={() => deactivateDirectory(directory.id)}>비활성화</button>}</div></div>)}
          {!directories.length && <span className="muted">등록된 디렉터리가 없습니다.</span>}
        </div>
      </section>
    </div>}
  </div>
}
