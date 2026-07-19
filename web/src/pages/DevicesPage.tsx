import { useEffect, useState } from 'react'
import { api } from '../api'
import { Device } from '../types'

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [error, setError] = useState('')

  async function load() {
    try {
      setDevices(await api.get<Device[]>('/devices'))
    } catch (e) {
      setError(e instanceof Error ? e.message : '조회 실패')
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000) // NF-102: 5초 이내 주기 갱신
    return () => clearInterval(timer)
  }, [])

  async function remove(id: number) {
    if (!confirm('이 기기를 삭제할까요?')) return
    await api.delete(`/devices/${id}`)
    load()
  }

  async function rename(d: Device) {
    const name = prompt('새 기기 이름을 입력하세요:', d.name)
    if (!name || name === d.name) return
    try {
      await api.patch(`/devices/${d.id}`, { name })
      load()
    } catch (e) {
      alert(e instanceof Error ? e.message : '이름 변경 실패')
    }
  }

  return (
    <div>
      <h1>기기 관리</h1>
      <p className="subtitle">
        등록된 Worker Node 목록입니다. 새 기기는 해당 기기에서{' '}
        <code>python -m agent register</code> 명령으로 등록하세요.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>이름</th><th>사양</th><th>허용 폴더</th><th>상태</th><th></th>
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => (
              <tr key={d.id}>
                <td><strong>{d.name}</strong></td>
                <td style={{ fontSize: 13, color: 'var(--muted)' }}>
                  {String(d.specs.os ?? '')} · CPU {String(d.specs.cpu_count ?? '?')}코어 · RAM{' '}
                  {String(d.specs.ram_gb ?? '?')}GB
                  {d.specs.cpu_percent != null && ` · 사용률 ${d.specs.cpu_percent}%`}
                </td>
                <td style={{ fontSize: 13 }}>
                  {(d.allowed_folders ?? []).length > 0 ? d.allowed_folders.join(', ') : '—'}
                </td>
                <td>
                  <span className={`badge ${d.online ? 'online' : 'offline'}`}>
                    {d.online ? '온라인' : '오프라인'}
                  </span>
                </td>
                <td>
                  <div className="row" style={{ gap: 6 }}>
                    <button className="btn sm ghost" onClick={() => rename(d)}>이름 변경</button>
                    <button className="btn sm danger" onClick={() => remove(d.id)}>삭제</button>
                  </div>
                </td>
              </tr>
            ))}
            {devices.length === 0 && (
              <tr><td colSpan={5} style={{ color: 'var(--muted)' }}>등록된 기기가 없습니다.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
