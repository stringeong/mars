import { FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Service } from '../types'

export default function ServicesPage() {
  const [services, setServices] = useState<Service[]>([])
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.get<Service[]>('/services').then(setServices).catch(() => {})
  }, [])

  async function generate(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const service = await api.post<Service>('/services/generate', { prompt })
      navigate(`/services/${service.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '생성 실패')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1>서비스</h1>
      <p className="subtitle">만들고 싶은 서비스를 자연어로 설명하면 에이전트 구성과 워크플로우(DAG)를 자동 생성합니다.</p>

      <div className="card">
        <h2>새 서비스 생성</h2>
        <form onSubmit={generate}>
          <textarea
            placeholder="예: 내 이력서와 포트폴리오를 분석해서 지원 가능한 직무를 추천하고, 각 직무별 자기소개서 초안을 만들어 줘"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            required
            minLength={5}
          />
          {error && <div className="error">{error}</div>}
          <div style={{ marginTop: 12 }}>
            <button className="btn" disabled={loading}>
              {loading ? '워크플로우 생성 중... (최대 2분)' : '워크플로우 생성'}
            </button>
          </div>
        </form>
      </div>

      <div className="card">
        <h2>내 서비스</h2>
        <table>
          <thead>
            <tr><th>이름</th><th>설명</th><th>에이전트 수</th><th>수정일</th></tr>
          </thead>
          <tbody>
            {services.map((s) => (
              <tr key={s.id} className="clickable" onClick={() => navigate(`/services/${s.id}`)}>
                <td><strong>{s.name}</strong></td>
                <td style={{ color: 'var(--muted)', fontSize: 13 }}>
                  {s.description.slice(0, 60)}{s.description.length > 60 ? '…' : ''}
                </td>
                <td>{s.graph?.nodes?.length ?? 0}</td>
                <td style={{ fontSize: 13 }}>{new Date(s.updated_at).toLocaleString('ko-KR')}</td>
              </tr>
            ))}
            {services.length === 0 && (
              <tr><td colSpan={4} style={{ color: 'var(--muted)' }}>아직 생성된 서비스가 없습니다.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
