import { ValidationResult } from '../types'
import { stageSummary } from '../workflow'

export default function ValidationPanel({ validation, nodeNames, onSelectNode, showStages = true }: {
  validation: ValidationResult | null
  nodeNames: Record<string, string>
  onSelectNode?: (nodeId: string) => void
  showStages?: boolean
}) {
  if (!validation) return <div className="validation-panel"><span className="muted">구성을 검사하는 중…</span></div>
  const issues = [...validation.errors, ...validation.warnings]

  return <div className="validation-panel">
    <div className="validation-summary">
      {validation.errors.length > 0 && <span className="validation-count error">오류 {validation.errors.length}</span>}
      {validation.warnings.length > 0 && <span className="validation-count warning">경고 {validation.warnings.length}</span>}
      {!issues.length && <span className="validation-count ok">문제 없음</span>}
    </div>
    {issues.length > 0 && <ul className="validation-list">
      {issues.map((issue, index) => <li key={`${issue.code}-${index}`} className={issue.severity}>
        <button type="button" disabled={!onSelectNode || !issue.node_ids.length} onClick={() => issue.node_ids[0] && onSelectNode?.(issue.node_ids[0])}>
          {issue.message}
        </button>
      </li>)}
    </ul>}
    {showStages && validation.stages.length > 0 && <div className="stage-preview">
      <span className="eyebrow">실행 단계 미리보기</span>
      <ol>
        {validation.stages.map((nodeIds, index) => {
          const names = nodeIds.map((nodeId) => nodeNames[nodeId] ?? nodeId)
          return <li key={index} title={names.join(', ')}><strong>{index + 1}단계</strong><span>{stageSummary(names)}</span></li>
        })}
      </ol>
    </div>}
  </div>
}
