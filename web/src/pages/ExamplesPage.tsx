import { useEffect, useState } from 'react'
import { api } from '../api'
import { CommunityCard, ExampleCard, PublicFooter, PublicHeader } from '../components/PublicChrome'
import { EXAMPLE_GROUPS, EXAMPLES, ExampleGroup, Fit, FITS } from '../examples'
import { CommunityWorkflow } from '../types'

/** 활용 예시 모음: 분야·잘 맞는 이유·검색으로 고르고, 마음에 드는 예시로 바로 워크플로우를 만든다 */
export default function ExamplesPage() {
  const [examplesOpen, setExamplesOpen] = useState(false)
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

  return <div className="mk-page">
    <PublicHeader />

    <section className="mk-dl-hero">
      <div className="mk-shell">
        <span className="mk-kicker">커뮤니티</span>
        <h1>함께 만든 워크플로우를 써 보세요</h1>
        <p>다른 사용자가 공유한 흐름을 내 워크플로우로 가져와 바로 고쳐 쓸 수 있어요. 처음 시작할 때는 추천 예시도 함께 살펴보세요.</p>
      </div>
    </section>

    <section className="mk-section">
      <div className="mk-shell">
        <div className="mk-community-section mk-community-section-first">
          <div className="mk-community-head"><b>커뮤니티가 공유한 워크플로우</b><small>{community.length}개</small><span className="mk-beta">시험 기능</span></div>
          {community.length
            ? <div className="mk-examples">{community.map((item) => <CommunityCard key={item.id} item={item} />)}</div>
            : <p className="mk-community-empty">아직 공유된 워크플로우가 없어요. 편집 화면의 '커뮤니티에 공유'로 내 워크플로우를 올려 보세요.</p>}
        </div>

        <section className="mk-recommended-section" aria-labelledby="recommended-examples-title">
          <div className="mk-recommended-head">
            <div><b id="recommended-examples-title">추천 예시</b><small>처음 시작할 때 참고할 수 있는 {EXAMPLES.length}개</small></div>
            <button type="button" className="mk-more" aria-expanded={examplesOpen} aria-controls="recommended-examples" onClick={() => setExamplesOpen((open) => !open)}>
              {examplesOpen ? '예시 접기' : '예시 보기'}
            </button>
          </div>
          {examplesOpen && <div id="recommended-examples">
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
        <div className="mk-community-head"><b>조건에 맞는 예시</b><small>{shown.length}개</small></div>
        <div className="mk-examples">
          {shown.map((example) => <ExampleCard key={example.title} example={example} />)}
        </div>
        {!shown.length && <p className="mk-examples-empty">조건에 맞는 예시가 없어요. 검색어나 필터를 바꿔 보세요.</p>}
        <p className="mk-examples-note">질문 하나로 끝나는 일이나 최신 정보 검색은 일반 챗봇이 더 빨라요. 여러 단계로 나뉘는 일에서 차이가 커져요.</p>
          </div>}
        </section>
      </div>
    </section>

    <PublicFooter />
  </div>
}
