import { useEffect, useState } from 'react'
import { api } from '../api'
import { CommunityWorkflow, Service } from '../types'

type Props = {
  serviceId: number
  defaultTitle: string
  defaultDescription: string
  // 공유 전에 편집 중인 내용을 저장한다. 저장에 실패하면 null
  save: () => Promise<Service | null>
  onClose: () => void
}

/** 내 워크플로우를 활용 예시 페이지의 커뮤니티 목록에 공유하거나 내린다 */
export default function ShareDialog({ serviceId, defaultTitle, defaultDescription, save, onClose }: Props) {
  const [entry, setEntry] = useState<CommunityWorkflow | null>(null)
  const [title, setTitle] = useState(defaultTitle.slice(0, 60))
  const [description, setDescription] = useState(defaultDescription.slice(0, 500))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<CommunityWorkflow | null>(`/services/${serviceId}/publication`).then((current) => {
      setEntry(current)
      if (current) { setTitle(current.title); setDescription(current.description) }
    }).catch(() => {})
  }, [serviceId])

  async function publish() {
    setBusy(true); setError('')
    try {
      if (!(await save())) { setError('먼저 저장 오류를 고쳐 주세요.'); return }
      setEntry(await api.put<CommunityWorkflow>(`/services/${serviceId}/publication`, { title: title.trim(), description: description.trim() }))
    } catch (cause) { setError(cause instanceof Error ? cause.message : '공유하지 못했습니다.') }
    finally { setBusy(false) }
  }
  async function unpublish() {
    if (!confirm('커뮤니티 공유를 중단할까요? 이미 가져간 사람의 사본은 그대로 남습니다.')) return
    setBusy(true); setError('')
    try { await api.delete(`/services/${serviceId}/publication`); setEntry(null) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '공유를 중단하지 못했습니다.') }
    finally { setBusy(false) }
  }

  return <div className="file-library-modal-backdrop" role="presentation" onMouseDown={onClose}>
    <section className="file-library-modal share-dialog" role="dialog" aria-modal="true" aria-labelledby="share-title" onMouseDown={(event) => event.stopPropagation()}>
      <header><div><span className="eyebrow">COMMUNITY</span><h2 id="share-title">{entry ? '커뮤니티에 공유 중' : '커뮤니티에 공유'}</h2></div><button type="button" className="modal-close" aria-label="닫기" onClick={onClose}>×</button></header>
      <p>공유하면 활용 예시 페이지에 올라가고, 다른 사람이 이 구성을 자기 워크플로우로 가져갈 수 있어요.</p>
      <div className="share-body">
        <label htmlFor="share-name">제목</label>
        <input id="share-name" value={title} maxLength={60} onChange={(event) => setTitle(event.target.value)} />
        <label htmlFor="share-desc">설명</label>
        <textarea id="share-desc" rows={3} value={description} maxLength={500} placeholder="어떤 일에 쓰는 구성인지 적어 주세요" onChange={(event) => setDescription(event.target.value)} />
        <div className="share-note">
          <b>공유되는 것</b> 에이전트 이름·역할 프롬프트·모델, 블록 연결, 필요한 파일 안내
          <br /><b>빠지는 것</b> 지정한 워커, 공유 디렉토리, 올린 파일, 블록에 적은 텍스트 입력
        </div>
        {entry && <small className="share-meta">{entry.import_count}명이 가져갔어요 · 마지막 공유 {new Date(entry.updated_at).toLocaleString()}</small>}
        {error && <p className="error">{error}</p>}
      </div>
      <footer>
        <span>{entry ? '다시 공유하면 지금 구성으로 바뀌어요.' : '지금 편집 중인 내용을 저장한 뒤 공유해요.'}</span>
        <div>
          {entry && <button type="button" className="btn sm ghost danger-text" disabled={busy} onClick={unpublish}>공유 중단</button>}
          <button type="button" className="btn sm" disabled={busy || title.trim().length < 2} onClick={publish}>{busy ? '처리 중…' : entry ? '최신 구성으로 다시 공유' : '공유하기'}</button>
        </div>
      </footer>
    </section>
  </div>
}
