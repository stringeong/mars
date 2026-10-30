import { useEffect, useState } from 'react'
import { api } from '../api'
import { CommunityCard, ExampleCard, PublicFooter, PublicHeader } from '../components/PublicChrome'
import { EXAMPLE_GROUPS, EXAMPLES, ExampleGroup, Fit, FITS } from '../examples'
import { CommunityWorkflow } from '../types'

/** 활용 예시 모음: 분야·잘 맞는 이유·검색으로 고르고, 마음에 드는 예시로 바로 워크플로우를 만든다 */
export default function ExamplesPage() {
  const [group, setGroup] = useState<ExampleGroup>('전체')
  const [fit, setFit] = useState<Fit | null>(null)
  const [query, setQuery] = useState('')
  const [community, setCommunity] = useState<CommunityWorkflow[]>([])
  useEffect(() => { window.scrollTo(0, 0) }, [])
  useEffect(() => { api.get<CommunityWorkflow[]>('/community/workflows').then((list) => setCommunity(Array.isArray(list) ? list : [])).catch(() => {}) }, [])

  const keyword = query.trim().toLowerCase()
  // 강점이 잘 드러나는 예시를 먼저 보여준다
  const ordered = [...EXAMPLES.filter((example) => example.featured), ...EXAMPLES.filter((example) => !example.featured)]
  const shown = ordered.filter((example) => (group === '전체' || example.group === group)
    && (!fit || example.fits.includes(fit))
    && (!keyword || `${example.title} ${example.prompt} ${example.keywords ?? ''}`.toLowerCase().includes(keyword)))
  // 커뮤니티 공유는 분야·이유 태그가 없으니 검색어만 적용한다
  const sharedShown = community.filter((item) => !keyword
    || `${item.title} ${item.description} ${item.author} ${item.graph.nodes.map((node) => node.name).join(' ')}`.toLowerCase().includes(keyword))

  return <div className="mk-page">
    <PublicHeader />

    <section className="mk-dl-hero">
      <div className="mk-shell">
        <span className="mk-kicker">활용 예시 {EXAMPLES.length}개</span>
        <h1>M.A.R.S에 이런 일을 맡겨 보세요</h1>
        <p>여러 단계로 나뉘는 일, 밖으로 보내기 싫은 자료, 입력만 바뀌는 반복 작업에서 특히 잘 맞아요. 마음에 드는 예시로 바로 시작할 수 있어요.</p>
      </div>
    </section>

    <section className="mk-section">
      <div className="mk-shell">
        <div className="mk-example-tools">
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="예시 검색 (예: 계약서, 마스킹, 로그)" aria-label="예시 검색" />
          <div className="mk-filter" role="tablist" aria-label="분야">
            {EXAMPLE_GROUPS.map((name) => <button key={name} type="button" role="tab" aria-selected={group === name} className={group === name ? 'active' : ''} onClick={() => setGroup(name)}>
              {name}<small>{name === '전체' ? EXAMPLES.length : EXAMPLES.filter((example) => example.group === name).length}</small>
            </button>)}
          </div>
          <div className="mk-filter mk-filter-fits" aria-label="잘 맞는 이유">
            <span>잘 맞는 이유</span>
            {FITS.map((name) => <button key={name} type="button" aria-pressed={fit === name} className={fit === name ? 'active' : ''} onClick={() => setFit(fit === name ? null : name)}>{name}</button>)}
          </div>
        </div>
        <div className="mk-community-head"><b>추천 예시</b><small>{shown.length}개</small></div>
        <div className="mk-examples">
          {shown.map((example) => <ExampleCard key={example.title} example={example} />)}
        </div>
        {!shown.length && <p className="mk-examples-empty">조건에 맞는 예시가 없어요. 검색어나 필터를 바꿔 보세요.</p>}
        <p className="mk-examples-note">질문 하나로 끝나는 일이나 최신 정보 검색은 일반 챗봇이 더 빨라요. 여러 단계로 나뉘는 일에서 차이가 커져요.</p>
        {/* 커뮤니티 공유는 시험 기능이라 추천 예시 뒤에 둔다 */}
        {(group === '전체' && !fit) && <div className="mk-community-section">
          <div className="mk-community-head"><b>커뮤니티가 공유한 워크플로우</b><small>{community.length}개</small><span className="mk-beta">시험 기능</span></div>
          {sharedShown.length
            ? <div className="mk-examples">{sharedShown.map((item) => <CommunityCard key={item.id} item={item} />)}</div>
            : <p className="mk-community-empty">{community.length ? '검색어에 맞는 공유 워크플로우가 없어요.' : '아직 공유된 워크플로우가 없어요. 편집 화면의 \'커뮤니티에 공유\'로 내 워크플로우를 올려 보세요.'}</p>}
        </div>}
      </div>
    </section>

    <PublicFooter />
  </div>
}
