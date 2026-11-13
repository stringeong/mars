import { useEffect, useState } from 'react'
import { api } from '../api'
import { CommunityCard, ExampleCard, PublicFooter, PublicHeader } from '../components/PublicChrome'
import { EXAMPLE_GROUPS, EXAMPLES, ExampleGroup } from '../examples'
import { CommunityWorkflow } from '../types'

/** 커뮤니티 공유 / 추천 예시를 탭으로 나눠 보여주고, 검색과 분야로 고른다 */
export default function ExamplesPage() {
  const [tab, setTab] = useState<'community' | 'examples' | null>(null)
  const [group, setGroup] = useState<ExampleGroup>('전체')
  const [query, setQuery] = useState('')
  const [community, setCommunity] = useState<CommunityWorkflow[] | null>(null)
  useEffect(() => { window.scrollTo(0, 0) }, [])
  useEffect(() => { api.get<CommunityWorkflow[]>('/community/workflows').then((list) => setCommunity(Array.isArray(list) ? list : [])).catch(() => setCommunity([])) }, [])
  // 공유된 워크플로우가 있으면 커뮤니티 탭부터, 없으면 추천 예시부터 보여준다
  const active = tab ?? (community && community.length ? 'community' : 'examples')

  const keyword = query.trim().toLowerCase()
  // 강점이 잘 드러나는 예시를 먼저 보여준다
  const ordered = [...EXAMPLES.filter((example) => example.featured), ...EXAMPLES.filter((example) => !example.featured)]
  const shown = ordered.filter((example) => (group === '전체' || example.group === group)
    && (!keyword || `${example.title} ${example.prompt} ${example.keywords ?? ''}`.toLowerCase().includes(keyword)))
  const shared = (community ?? []).filter((item) => !keyword || `${item.title} ${item.description ?? ''} ${item.author}`.toLowerCase().includes(keyword))

  return <div className="mk-page">
    <PublicHeader />

    <section className="mk-dl-hero">
      <div className="mk-shell">
        <span className="mk-kicker">커뮤니티</span>
        <h1>함께 만든 워크플로우를 써 보세요</h1>
        <p>공유된 흐름을 내 워크플로우로 가져오거나, 추천 예시로 바로 시작해요.</p>
      </div>
    </section>

    <section className="mk-section">
      <div className="mk-shell">
        <div className="mk-gallery-bar">
          <div className="mk-tabs" role="tablist" aria-label="보기">
            <button type="button" role="tab" aria-selected={active === 'community'} className={active === 'community' ? 'active' : ''} onClick={() => setTab('community')}>커뮤니티 공유<small>{community?.length ?? 0}</small></button>
            <button type="button" role="tab" aria-selected={active === 'examples'} className={active === 'examples' ? 'active' : ''} onClick={() => setTab('examples')}>추천 예시<small>{EXAMPLES.length}</small></button>
          </div>
          <input className="mk-gallery-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={active === 'community' ? '공유된 워크플로우 검색' : '예시 검색 (예: 계약서, 마스킹, 로그)'} aria-label="검색" />
        </div>

        {active === 'community' && <>
          {shared.length
            ? <div className="mk-examples">{shared.map((item) => <CommunityCard key={item.id} item={item} />)}</div>
            : <p className="mk-community-empty">{community?.length ? '검색 결과가 없어요.' : "아직 공유된 워크플로우가 없어요. 편집 화면의 ⋯ 메뉴에서 '커뮤니티에 공유'로 올려 보세요."}</p>}
        </>}

        {active === 'examples' && <>
          <div className="mk-filter" role="tablist" aria-label="분야">
            {EXAMPLE_GROUPS.map((name) => <button key={name} type="button" role="tab" aria-selected={group === name} className={group === name ? 'active' : ''} onClick={() => setGroup(name)}>
              {name}<small>{name === '전체' ? EXAMPLES.length : EXAMPLES.filter((example) => example.group === name).length}</small>
            </button>)}
          </div>
          <div className="mk-examples">
            {shown.map((example) => <ExampleCard key={example.title} example={example} />)}
          </div>
          {!shown.length && <p className="mk-examples-empty">조건에 맞는 예시가 없어요. 검색어나 분야를 바꿔 보세요.</p>}
          <p className="mk-examples-note">질문 하나로 끝나는 일이나 최신 정보 검색은 일반 챗봇이 더 빨라요. 여러 단계로 나뉘는 일에서 차이가 커져요.</p>
        </>}
      </div>
    </section>

    <PublicFooter />
  </div>
}
