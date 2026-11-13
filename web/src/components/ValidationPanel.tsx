import { ValidationIssue, ValidationResult } from '../types'
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
      {groupIssues(issues).map((group, index) => <li key={`${group.code}-${index}`} className={group.severity}>
        {group.items.length === 1
          ? <button type="button" disabled={!onSelectNode || !group.items[0].node_ids.length} onClick={() => group.items[0].node_ids[0] && onSelectNode?.(group.items[0].node_ids[0])}>{group.items[0].message}</button>
          : <>
            <span className="validation-group-title">{group.title} · 블록 {group.items.length}개</span>
            <span className="validation-group-nodes">{group.items.map((issue, itemIndex) => <button type="button" key={itemIndex} disabled={!onSelectNode || !issue.node_ids.length} onClick={() => issue.node_ids[0] && onSelectNode?.(issue.node_ids[0])}>{issue.node_ids.map((nodeId) => nodeNames[nodeId] ?? nodeId).join(', ') || issue.message}</button>)}</span>
          </>}
        {group.items.some((issue) => issue.resolvable_by_run_prompt) && <small>실행 화면에서 실행 프롬프트를 입력하면 해소됩니다.</small>}
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

/** 같은 종류의 문제가 여러 블록에서 나오면 한 줄로 묶는다. "'거래 분류' 블록에 필요한 파일이…" → "필요한 파일이…" */
function groupIssues(issues: ValidationIssue[]) {
  const groups: { code: string; severity: ValidationIssue['severity']; title: string; items: ValidationIssue[] }[] = []
  for (const issue of issues) {
    const title = issue.message.replace(/^'[^']*'\s*블록(에|의|이|은|는)?\s*/, '').trim()
    const found = groups.find((group) => group.code === issue.code && group.severity === issue.severity && group.title === title)
    if (found) found.items.push(issue)
    else groups.push({ code: issue.code, severity: issue.severity, title, items: [issue] })
  }
  return groups
}
