import { Handle, Position } from '@xyflow/react'

export interface BlockCategory {
  tag: string
  color: string
  bg: string
}

const CATEGORIES: { pattern: RegExp; cat: BlockCategory }[] = [
  { pattern: /수집|조사|검색|리서치/, cat: { tag: '수집', color: '#0d9488', bg: '#f0fdfa' } },
  { pattern: /분석|비교|계산/, cat: { tag: '분석', color: '#2563eb', bg: '#eff6ff' } },
  { pattern: /검토|평가|검증|리뷰/, cat: { tag: '검토', color: '#d97706', bg: '#fffbeb' } },
  { pattern: /정리|요약|통합|일정|생성|작성|보고/, cat: { tag: '정리', color: '#7c3aed', bg: '#f5f3ff' } },
]

export function categoryOf(name: string): BlockCategory {
  for (const { pattern, cat } of CATEGORIES) {
    if (pattern.test(name)) return cat
  }
  return { tag: '에이전트', color: '#64748b', bg: '#f8fafc' }
}

export default function AgentBlockNode({ data, selected }: { data: any; selected?: boolean }) {
  const cat = categoryOf(String(data.label ?? ''))
  return (
    <div
      className={`agent-block${selected ? ' selected' : ''}`}
      style={{ borderColor: cat.color, background: cat.bg }}
    >
      <div className="agent-block-tag" style={{ background: cat.color }}>{cat.tag}</div>
      <div className="agent-block-name">{data.label}</div>
      {data.model ? <div className="agent-block-model">{data.model}</div> : null}
      <Handle type="target" position={Position.Left} className="block-handle" />
      <Handle type="source" position={Position.Right} className="block-handle" />
    </div>
  )
}
