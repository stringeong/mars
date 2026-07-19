import { useEffect, useState } from 'react'
import { api } from '../api'

interface EventItem {
  id: number
  event_type: string
  detail: string
  created_at: string
}

const TYPE_BADGE: Record<string, string> = {
  '로그인 실패': 'failed',
  '실행 실패': 'failed',
  '회원정보 수정 실패': 'failed',
  '실행 완료': 'done',
  '로그인 성공': 'done',
  '실행 중단': 'cancelled',
}

export default function EventsPage() {
  const [items, setItems] = useState<EventItem[]>([])

  useEffect(() => {
    api.get<EventItem[]>('/auth/events').then(setItems).catch(() => {})
  }, [])

  return (
    <div>
      <h1>활동 로그</h1>
      <p className="subtitle">
        로그인, 기기 등록, 서비스 실행 등 계정의 주요 이벤트 기록입니다. 실패한 로그인 시도도 함께 남습니다.
      </p>
      <div className="card">
        <table>
          <thead>
            <tr><th>시각</th><th>이벤트</th><th>상세</th></tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.id}>
                <td style={{ fontSize: 13, whiteSpace: 'nowrap' }}>
                  {new Date(e.created_at).toLocaleString('ko-KR')}
                </td>
                <td>
                  <span className={`badge ${TYPE_BADGE[e.event_type] ?? 'pending'}`}>{e.event_type}</span>
                </td>
                <td style={{ fontSize: 13, color: 'var(--muted)' }}>{e.detail || '—'}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={3} style={{ color: 'var(--muted)' }}>기록이 없습니다.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
