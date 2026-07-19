import { FormEvent, useEffect, useState } from 'react'
import { api } from '../api'

interface Me {
  id: number
  username: string
  email: string
}

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null)
  const [email, setEmail] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<Me>('/auth/me').then((m) => {
      setMe(m)
      setEmail(m.email)
    }).catch(() => {})
  }, [])

  async function save(e: FormEvent) {
    e.preventDefault()
    setMessage('')
    setError('')
    try {
      const body: Record<string, string> = { current_password: currentPassword }
      if (email && email !== me?.email) body.email = email
      if (newPassword) body.new_password = newPassword
      const updated = await api.patch<Me>('/auth/me', body)
      setMe(updated)
      setEmail(updated.email)
      setCurrentPassword('')
      setNewPassword('')
      setMessage('회원정보가 수정되었습니다.')
    } catch (err) {
      setError(err instanceof Error ? err.message : '수정 실패')
    }
  }

  if (!me) return <div>불러오는 중...</div>

  return (
    <div>
      <h1>내 정보</h1>
      <p className="subtitle">이메일과 비밀번호를 변경할 수 있습니다. 본인 확인을 위해 현재 비밀번호가 필요합니다.</p>
      <div className="card" style={{ maxWidth: 480 }}>
        <form onSubmit={save}>
          <label>아이디</label>
          <input value={me.username} disabled />
          <label>이메일</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <label>새 비밀번호 (변경할 때만 입력)</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            minLength={6}
            placeholder="6자 이상"
          />
          <label>현재 비밀번호 (필수)</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
          />
          {message && <div style={{ color: 'var(--success)', fontSize: 13, marginTop: 8 }}>{message}</div>}
          {error && <div className="error">{error}</div>}
          <button className="btn" style={{ marginTop: 16 }}>저장</button>
        </form>
      </div>
    </div>
  )
}
