import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { ExecutionListItem } from '../types'
import { executionStatusLabel, generationLabel, inputFilesSummary, shortDateTime } from '../workflow'

const statuses = ['all', 'completed', 'running', 'failed'] as const

export default function HistoryPage() {
  const [items, setItems] = useState<ExecutionListItem[]>([])
  const [filter, setFilter] = useState<(typeof statuses)[number]>('all')
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  useEffect(() => { api.get<ExecutionListItem[]>('/executions').then(setItems).catch(() => {}) }, [])
  const visibleItems = useMemo(() => items.filter((item) =>
    (filter === 'all' || item.status === filter) && `${item.service_name} ${item.run_prompt}`.toLowerCase().includes(query.toLowerCase()),
  ), [filter, items, query])

  return <div className="history-page">
    <header className="page-topbar">
      <div><div className="breadcrumb">M.A.R.S <span>/</span> 실행 이력</div><h1>실행 이력</h1><p>실행 결과와 에이전트별 출력을 확인하고 다시 실행할 수 있어요.</p></div>
    </header>
    {/* 실행 목록은 표 하나로 보여준다. 검색·상태 필터도 이 표에 건다 */}
    <section className="history-overview">
      {/* 상태별 개수를 한눈에 (누르면 그 상태만 보기) */}
      <div className="history-stats">{(['completed', 'running', 'failed'] as const).map((status) => <button type="button" key={status} className={`history-stat ${status}${filter === status ? ' active' : ''}`} onClick={() => setFilter(filter === status ? 'all' : status)}><strong>{items.filter((item) => item.status === status).length}</strong><span>{executionStatusLabel(status)}</span></button>)}</div>
            <div className="history-table-card">
        <div className="section-heading history-table-heading">
          <div><span className="eyebrow">전체 기록</span><h2>실행 <small>{visibleItems.length >= 100 ? '100+' : visibleItems.length}</small></h2></div>
          <div className="history-table-tools">
            <div className="history-filters">{statuses.map((status) => <button type="button" className={filter === status ? 'active' : ''} key={status} onClick={() => setFilter(status)}>{status === 'all' ? '전체' : executionStatusLabel(status)}</button>)}</div>
            <input className="execution-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="실행 검색" />
          </div>
        </div>
        <div className="history-table-wrap"><table><thead><tr><th>워크플로우</th><th>상태</th><th>생성 모델</th><th>시작 시각</th><th /></tr></thead><tbody>
          {visibleItems.map((item) => <tr className="clickable" key={item.id} onClick={() => navigate(`/executions/${item.id}`)}>
            <td><strong>{item.service_name}</strong><small>#{item.id} · {item.run_prompt || '실행 프롬프트 없음'} · 입력: {inputFilesSummary(item.input_files)}</small></td>
            <td><span className={`status-pill ${item.status}`}>{executionStatusLabel(item.status)}</span></td>
            <td><small className="history-model">{generationLabel(item.generation_info)}</small></td>
            <td>{shortDateTime(item.created_at)}</td>
            <td>→</td>
          </tr>)}
          {!visibleItems.length && <tr><td colSpan={5} className="empty-cell">{items.length ? '검색 결과가 없어요.' : '실행하면 여기에 기록이 쌓여요.'}</td></tr>}
        </tbody></table></div>
      </div>
    </section>
  </div>
}
