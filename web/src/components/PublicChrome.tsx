import { Link, NavLink } from 'react-router-dom'
import { getToken } from '../api'
import { Example } from '../examples'
import { GITHUB_URL } from '../release'

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
