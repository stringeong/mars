import AppIcon from '../components/AppIcon'
import { FormEvent, useEffect, useState } from 'react'
import { api, getDeviceDirectories } from '../api'
import { Device, DeviceState, DirectoryInspection, SharedDirectory } from '../types'
import { sortDevices, timeAgo } from '../workflow'

const emptyDirectory = { alias: '', local_path: '', permission: 'read' as const }

/** 'Darwin 27.0.0'처럼 커널 이름으로 오는 맥은 macOS로 보여준다. */
function osLabel(device: Device) {
  const os = String(device.specs.os ?? '')
  return /^darwin/i.test(os) ? 'macOS' : os || '-'
}

const STATE_LABELS: Record<DeviceState, string> = {
  offline: '오프라인',
  running: '실행 중',
  paused: '일시 중지',
  user_active: '사용자 사용 중',
  busy: '다른 프로그램 사용 중',
  available: '작업 가능',
}

/** 마지막 하트비트 뒤 지난 시간. 30초가 지나면 오프라인이 되는 게 정상이다 */
function lastSeen(device: Device, now: number) {
  if (!device.last_heartbeat) return '응답 기록 없음'
  const seconds = Math.max(0, Math.round((now - new Date(device.last_heartbeat).getTime()) / 1000))
  return seconds < 60 ? `마지막 응답 ${seconds}초 전` : `마지막 응답 ${timeAgo(device.last_heartbeat)}`
}

/** 지금 작업을 받을 수 있는지(배지)와 마지막 응답 시각. 마우스를 올리면 이유가 보인다 */
function stateCell(device: Device, now: number) {
  const state = device.state ?? (device.online ? 'available' : 'offline')
  return <span className="device-state" title={device.state_reason}><span className={`badge device-badge ${state}`}>{STATE_LABELS[state]}</span><small>{lastSeen(device, now)}</small></span>
}

/** 온라인이면 지금 CPU 사용률(M.A.R.S.와 다른 프로그램을 나눠서), 오프라인이면 표시하지 않는다 */
function usageCell(device: Device) {
  if (!device.online) return <span className="device-seen">-</span>
  const percent = Number(device.specs.cpu_percent)
  if (!Number.isFinite(percent)) return <span className="device-seen">-</span>
  const other = Number(device.specs.other_cpu_percent)
  const split = device.specs.other_cpu_percent != null && Number.isFinite(other)
  return <span className="device-usage" title={split ? `M.A.R.S. ${Math.round(Number(device.specs.mars_cpu_percent) || 0)}% · 다른 프로그램 ${Math.round(other)}%` : undefined}><i><b style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} /></i>{Math.round(percent)}%{split && <small>다른 프로그램 {Math.round(other)}%</small>}</span>
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [directories, setDirectories] = useState<SharedDirectory[]>([])
  const [name, setName] = useState('')
  const [maxCpu, setMaxCpu] = useState('')
  const [maxGpu, setMaxGpu] = useState('')
  const [minIdle, setMinIdle] = useState('')
  const [onOverload, setOnOverload] = useState<'ask' | 'continue' | 'release'>('ask')
  const [now, setNow] = useState(Date.now())
  const [directoryForm, setDirectoryForm] = useState(emptyDirectory)
  const [editingDirectoryId, setEditingDirectoryId] = useState<number | null>(null)
  const [inspections, setInspections] = useState<Record<number, DirectoryInspection>>({})
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [filter, setFilter] = useState<'all' | 'on' | 'off'>('all')

  const selected = devices.find((device) => device.id === selectedId) ?? null

  async function load() {
    try { setDevices(await api.get<Device[]>('/devices')); setNow(Date.now()) }
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
    setMinIdle(device.resource_limits.min_user_idle_min?.toString() ?? '')
    setOnOverload(device.resource_limits.on_overload ?? 'ask')
    setDirectoryForm(emptyDirectory)
    setEditingDirectoryId(null)
    setError('')
    try { setDirectories(await getDeviceDirectories(device.id)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '폴더 조회 실패') }
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
          min_user_idle_min: minIdle ? Number(minIdle) : null,
          on_overload: onOverload,
        },
      })
      await load()
      setMessage('워커 설정을 저장했습니다.')
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
      setMessage('등록한 폴더를 저장했어요.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '폴더 저장 실패') }
  }

  async function deactivateDirectory(directoryId: number) {
    if (!selected || !confirm('이 폴더를 비활성화할까요?')) return
    try {
      await api.delete(`/devices/${selected.id}/directories/${directoryId}`)
      setDirectories(await getDeviceDirectories(selected.id))
    } catch (cause) { setError(cause instanceof Error ? cause.message : '폴더 변경 실패') }
  }

  async function pollInspection(directoryId: number, remaining = 20): Promise<void> {
    if (!selected || remaining <= 0) return
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
    try {
      const inspection = await api.get<DirectoryInspection | null>(
        `/devices/${selected.id}/directories/${directoryId}/inspections/latest`,
      )
      if (!inspection) return
      setInspections((current) => ({ ...current, [directoryId]: inspection }))
      if (inspection.status === 'pending' || inspection.status === 'running') {
        await pollInspection(directoryId, remaining - 1)
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : '검사 결과 조회 실패') }
  }

  async function inspectDirectory(directoryId: number) {
    if (!selected) return
    try {
      const inspection = await api.post<DirectoryInspection>(
        `/devices/${selected.id}/directories/${directoryId}/inspections`,
      )
      setInspections((current) => ({ ...current, [directoryId]: inspection }))
      void pollInspection(directoryId)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '폴더 검사 요청 실패') }
  }

  async function removeDevice(deviceId: number) {
    if (!confirm('이 워커를 삭제할까요?')) return
    await api.delete(`/devices/${deviceId}`)
    if (selectedId === deviceId) setSelectedId(null)
    load()
  }

  return <div className="devices-page">
    <header className="page-topbar">
      <div><div className="breadcrumb">M.A.R.S <span>/</span> 워커</div><h1>워커 관리</h1><p>연결된 기기 상태를 보고, 자원 사용 한도와 접근할 폴더를 정해요.</p></div>
    </header>
    <h1>기기 관리</h1>
    <p className="subtitle">워커의 이름, 새 작업 수용 기준과 등록한 폴더를 관리해요.</p>
    {error && <div className="error">{error}</div>}
    {message && <div style={{ color: 'var(--success)', marginBottom: 10 }}>{message}</div>}
    <div className="card device-table-card">
      <div className="device-filter" role="tablist" aria-label="상태별 보기">
        {([['all', '전체', devices.length], ['on', '온라인', devices.filter((device) => device.online).length], ['off', '오프라인', devices.filter((device) => !device.online).length]] as const).map(([key, label, count]) => <button key={key} type="button" role="tab" aria-selected={filter === key} className={filter === key ? 'active' : ''} onClick={() => setFilter(key)}>{label} <b>{count}</b></button>)}
      </div>
      <table className="device-table"><colgroup><col className="c-name" /><col className="c-os" /><col className="c-cpu" /><col className="c-ram" /><col className="c-state" /><col className="c-use" /><col className="c-act" /></colgroup><thead><tr><th>이름</th><th>운영체제</th><th>CPU</th><th>RAM</th><th>상태</th><th>CPU 사용률</th><th aria-label="관리" /></tr></thead><tbody>
        {sortDevices(devices).filter((device) => filter === 'all' || (filter === 'on') === device.online).map((device) => <tr key={device.id} className={[device.online ? 'on' : 'off', selectedId === device.id ? 'selected-row' : ''].filter(Boolean).join(' ')} onClick={() => selectDevice(device)} title={`${device.name} 설정 열기`}>
          <td><span className="device-name"><AppIcon name="workers" /><strong>{device.name}</strong><span className="sr-only">{device.online ? '온라인' : '오프라인'}</span></span></td>
          <td>{osLabel(device)}</td>
          <td>{device.specs.cpu_count != null ? `${String(device.specs.cpu_count)}코어` : '-'}</td>
          <td>{device.specs.ram_gb != null ? `${String(device.specs.ram_gb)}GB` : '-'}</td>
          <td>{stateCell(device, now)}</td>
          <td>{usageCell(device)}</td>
          <td className="device-actions-cell"><div className="row device-actions"><button type="button" className="icon-btn" title="워커 설정" aria-label={`${device.name} 설정`} onClick={(event) => { event.stopPropagation(); selectDevice(device) }}><AppIcon name="settings" /></button><button type="button" className="icon-btn danger" title="워커 삭제" aria-label={`${device.name} 삭제`} onClick={(event) => { event.stopPropagation(); removeDevice(device.id) }}><AppIcon name="trash" /></button></div></td>
        </tr>)}
        {!devices.length && <tr><td colSpan={7} className="device-empty">등록된 워커가 없어요. 워커 프로그램을 설치하면 여기에 나타나요.</td></tr>}
      </tbody></table>
    </div>

    {selected && <div className="device-editor">
      <section className="card"><h2>{selected.name} 설정</h2>
        <form onSubmit={saveDevice}>
          <label>워커 이름</label><input value={name} onChange={(event) => setName(event.target.value)} required />
          <div className="resource-limit-grid">
            <div><label>CPU 수용 상한 (%)</label><input type="number" min="1" max="100" placeholder="제한 없음" value={maxCpu} onChange={(event) => setMaxCpu(event.target.value)} /></div>
            <div><label>GPU 수용 상한 (%)</label><input type="number" min="1" max="100" placeholder="제한 없음" value={maxGpu} onChange={(event) => setMaxGpu(event.target.value)} /></div>
          </div>
          <p className="muted">다른 프로그램이 쓰는 사용률이 상한 이상이면 이 워커에는 새 작업을 주지 않아요. M.A.R.S.가 돌리는 Ollama 부하는 빼고 계산해요.</p>
          <div className="resource-limit-grid">
            <div><label htmlFor="min-idle">자리 비움 기준 (분)</label><input id="min-idle" type="number" min="1" max="240" placeholder="꺼짐" value={minIdle} onChange={(event) => setMinIdle(event.target.value)} /></div>
            <div><label htmlFor="on-overload">실행 중 상한을 넘으면</label><select id="on-overload" value={onOverload} onChange={(event) => setOnOverload(event.target.value as typeof onOverload)}>
              <option value="ask">워커 화면에서 물어보기</option>
              <option value="continue">계속 실행</option>
              <option value="release">바로 다른 기기로 넘기기</option>
            </select></div>
          </div>
          <p className="muted">자리 비움 기준을 넣으면 키보드·마우스 입력이 그 시간 동안 없을 때만 작업을 받아요. 실행 중에 다른 프로그램 CPU 사용률이 30초 넘게 상한을 넘으면 위에서 고른 대로 처리하고, 넘긴 워커는 5분 동안 쉬어요.</p>
          {selected.state_reason && <p className="muted">지금 상태: <strong>{STATE_LABELS[selected.state ?? 'offline']}</strong> · {selected.state_reason}</p>}
          <button className="btn">워커 설정 저장</button>
        </form>
      </section>
      <section className="card"><h2>등록한 폴더</h2>
        <p className="muted">같은 별명으로 여러 워커에 등록하면, 워커마다 다른 로컬 경로를 하나의 폴더처럼 묶어서 써요.</p>
        <form onSubmit={saveDirectory} className="directory-form">
          <input placeholder="별명 (예: 프로젝트 자료)" value={directoryForm.alias} onChange={(event) => setDirectoryForm({ ...directoryForm, alias: event.target.value })} required />
          <input placeholder="이 워커의 로컬 경로" value={directoryForm.local_path} onChange={(event) => setDirectoryForm({ ...directoryForm, local_path: event.target.value })} required />
          <span className="directory-permission">읽기 전용</span>
          <button className="btn">{editingDirectoryId ? '수정 저장' : '폴더 추가'}</button>
          {editingDirectoryId && <button type="button" className="btn ghost" onClick={() => { setEditingDirectoryId(null); setDirectoryForm(emptyDirectory) }}>취소</button>}
        </form>
        <div className="directory-list">
          {directories.map((directory) => {
            const inspection = inspections[directory.id]
            const checking = inspection?.status === 'pending' || inspection?.status === 'running'
            return <div key={directory.id} className="directory-inspection"><div className="directory-row"><div><strong>{directory.alias}</strong><small>{directory.local_path} · 읽기 전용 · {directory.is_active ? '활성' : '비활성'}</small></div><div className="row"><button className="btn sm ghost" disabled={checking || !directory.is_active} onClick={() => inspectDirectory(directory.id)}>{checking ? '검사 중…' : '검사'}</button><button className="btn sm ghost" onClick={() => { setEditingDirectoryId(directory.id); setDirectoryForm({ alias: directory.alias, local_path: directory.local_path, permission: 'read' }) }}>수정</button>{directory.is_active && <button className="btn sm danger" onClick={() => deactivateDirectory(directory.id)}>비활성화</button>}</div></div>{inspection?.status === 'done' && <div className="inspection-files"><strong>파일 {inspection.files.length}개</strong>{inspection.files.length ? <ul>{inspection.files.map((file) => <li key={file}>{file}</li>)}</ul> : <span className="muted">표시 가능한 파일이 없습니다.</span>}</div>}{inspection?.status === 'failed' && <div className="inspection-error">검사 실패: {inspection.error}</div>}</div>
          })}
          {!directories.length && <span className="muted">등록한 폴더가 없어요.</span>}
        </div>
      </section>
    </div>}
  </div>
}
