import { Handle, Position } from '@xyflow/react'

export function categoryOf(name: string) {
  if (name.includes('분석') || name.includes('조사')) return { tag: 'ANALYZE', color: '#2563eb', bg: '#eff6ff' }
  if (name.includes('작성') || name.includes('생성')) return { tag: 'CREATE', color: '#7c3aed', bg: '#f5f3ff' }
  if (name.includes('검토') || name.includes('검증')) return { tag: 'REVIEW', color: '#059669', bg: '#ecfdf5' }
  return { tag: 'AGENT', color: '#4f46e5', bg: '#eef2ff' }
}

export default function AgentBlockNode({ data, selected }: { data: any; selected?: boolean }) {
  const category = categoryOf(String(data.label ?? ''))
  const directories: string[] = data.directories ?? []

  return (
    <div className={`agent-block scratch-agent${selected ? ' selected' : ''}`} style={{ borderColor: category.color, background: category.bg }}>
      <div className="agent-block-tag" style={{ background: category.color }}>{category.tag}</div>
      <div className="agent-block-name">{data.label}</div>
      <div className="agent-block-model">{data.model || '기본 모델'}</div>

      <div className="agent-resources">
        <div className="resource-slot worker-slot">
          <span>⚙ Worker</span>
          <strong>{data.workerName || '자동 배정'}</strong>
        </div>
        <div className="resource-slot directory-slot">
          <span>▣ Directory</span>
          <strong>{directories.length ? directories.join(', ') : '없음'}</strong>
        </div>
      </div>

      <Handle type="target" position={Position.Left} id="workflow-input" className="block-handle workflow-input-handle" />
      <Handle type="source" position={Position.Right} id="workflow-output" className="block-handle workflow-output-handle" />
    </div>
  )
}
