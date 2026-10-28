import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { api, getToken } from '../api'
import { Example } from '../examples'
import { GITHUB_URL } from '../release'
import { CommunityWorkflow, Service } from '../types'

/** 로그인 없이 보는 제품 소개·워커 다운로드 페이지의 머리글 */
export function PublicHeader() {
  const authed = !!getToken()
  return <header className="mk-header">
    <div className="mk-shell mk-header-inner">
      <Link to="/about" className="mk-logo" aria-label="M.A.R.S 홈"><span>M</span>M.A.R.S</Link>
      <nav className="mk-nav" aria-label="제품">
        <a href="/about#how">작동 방식</a>
        <a href="/about#features">기능</a>
        <a href="/about#privacy">데이터 보호</a>
        <NavLink to="/examples">활용 예시</NavLink>
        <NavLink to="/download">워커 다운로드</NavLink>
      </nav>
      <div className="mk-header-actions">
        {authed
          ? <Link className="mk-btn mk-btn-primary" to="/services">워크스페이스로 이동</Link>
          : <>
            <Link className="mk-btn mk-btn-ghost" to="/login">로그인</Link>
            <Link className="mk-btn mk-btn-primary" to="/login?mode=register">회원가입</Link>
          </>}
      </div>
    </div>
  </header>
}

export function PublicFooter() {
  return <footer className="mk-footer">
    <div className="mk-shell mk-footer-inner">
      <div>
        <div className="mk-logo"><span>M</span>M.A.R.S</div>
        <p>가진 컴퓨터들로 꾸리는 멀티 에이전트 AI 워크플로우</p>
      </div>
      <div className="mk-footer-links">
        <Link to="/about">제품 소개</Link>
        <Link to="/examples">활용 예시</Link>
        <Link to="/download">워커 다운로드</Link>
        <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub</a>
      </div>
    </div>
  </footer>
}

/** 활용 예시 카드. 로그인했으면 이 문장을 채운 채 첫 화면으로, 아니면 회원가입으로 보낸다 */
export function ExampleCard({ example }: { example: Example }) {
  const to = getToken() ? `/services?prompt=${encodeURIComponent(example.prompt)}` : '/login?mode=register'
  return <div className="mk-example">
    <span className="mk-example-group">{example.group}</span>
    <b>{example.title}</b>
    <p>“{example.prompt}”</p>
    <div className="mk-fits">{example.fits.map((fit) => <small key={fit}>{fit}</small>)}</div>
    <Link className="mk-example-use" to={to}>이 예시로 만들기 →</Link>
  </div>
}

/** 블록 이름을 실행 단계별로 묶는다. 같은 단계의 블록은 함께(병렬로) 실행된다 */
function stagesOf(graph: CommunityWorkflow['graph']) {
  const agents = graph.nodes.filter((node) => node.type === 'agent')
  const level = new Map<string, number>()
  const parents = (id: string) => graph.edges.filter((edge) => edge.target === id).map((edge) => edge.source)
  for (let pass = 0; pass < agents.length; pass += 1) {
    for (const node of agents) level.set(node.id, Math.max(0, ...parents(node.id).map((id) => (level.get(id) ?? 0) + 1)))
  }
  const stages: string[][] = []
  for (const node of agents) (stages[level.get(node.id) ?? 0] ??= []).push(node.name)
  return stages.filter(Boolean)
}

/** 커뮤니티가 공유한 워크플로우 카드. 로그인했으면 내 워크플로우로 복사해 편집 화면으로 간다 */
export function CommunityCard({ item }: { item: CommunityWorkflow }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const stages = stagesOf(item.graph)
  async function take() {
    if (!getToken()) { navigate('/login?mode=register'); return }
    setBusy(true)
    try {
      const service = await api.post<Service>(`/community/workflows/${item.id}/import`)
      navigate(`/services/${service.id}`)
    } catch (cause) {
      alert(cause instanceof Error ? cause.message : '가져오지 못했습니다.')
      setBusy(false)
    }
  }
  return <div className="mk-example mk-community">
    <span className="mk-example-group">커뮤니티 · {item.author}</span>
    <b>{item.title}</b>
    <p>{item.description || '설명이 없어요.'}</p>
    <ol className="mk-community-flow">{stages.map((names, index) => <li key={index}>{names.join(' + ')}</li>)}</ol>
    <small className="mk-community-meta">블록 {item.graph.nodes.length}개{item.import_count ? ` · ${item.import_count}명이 가져감` : ''}</small>
    <button type="button" className="mk-example-use" disabled={busy} onClick={take}>{busy ? '가져오는 중…' : '내 워크플로우로 가져오기 →'}</button>
  </div>
}
