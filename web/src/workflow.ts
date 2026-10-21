import { AgentNode, GenerationInfo, RunInputRecord, Task, ValidationIssue, ValidationResult } from './types'

export type FlagExplanation = { manual: boolean; reason: string }
export type AutoFlagReasons = { needsFile: FlagExplanation; final: FlagExplanation }

function longestPathLevels(ids: string[], pairs: { source: string; target: string }[]) {
  const indegree = new Map(ids.map((id) => [id, 0]))
  const children = new Map<string, string[]>(ids.map((id) => [id, []]))
  pairs.forEach(({ source, target }) => { children.get(source)!.push(target); indegree.set(target, indegree.get(target)! + 1) })
  const level = new Map(ids.map((id) => [id, 0]))
  const done = new Map<string, number>()
  const queue = ids.filter((id) => indegree.get(id) === 0)
  while (queue.length) {
    const current = queue.shift()!
    done.set(current, level.get(current)!)
    for (const child of children.get(current)!) {
      level.set(child, Math.max(level.get(child)!, level.get(current)! + 1))
      indegree.set(child, indegree.get(child)! - 1)
      if (indegree.get(child) === 0) queue.push(child)
    }
  }
  return done
}

/**
 * 서버 dag.apply_auto_flags와 같은 규칙으로 최종 블록·사용자 파일 필요를 정하고 이유를 함께 돌려준다.
 * 직접 지정한 값(*_manual)은 바꾸지 않는다.
 */
export function applyAutoFlags(agents: AgentNode[], edges: { source: string; target: string }[]) {
  const ids = agents.map((agent) => agent.id)
  const known = new Set(ids)
  const pairs = edges.filter((edge) => known.has(edge.source) && known.has(edge.target))
  const hasParent = new Set(pairs.map((edge) => edge.target))
  const hasChild = new Set(pairs.map((edge) => edge.source))
  const levels = longestPathLevels(ids, pairs)
  const next = agents.map((agent) => ({
    ...agent,
    needs_file: agent.needs_file_manual ? !!agent.needs_file : !!agent.needs_file_hint || !hasParent.has(agent.id),
    final: agent.final_manual ? !!agent.final : false,
  }))
  const manualFinal = next.find((agent) => agent.final_manual && agent.final)
  const sinks = manualFinal ? [] : next.filter((agent) => !hasChild.has(agent.id) && !agent.final_manual)
  const hinted = sinks.filter((agent) => agent.final_hint)
  const candidates = hinted.length ? hinted : sinks
  // 가장 뒤 단계, 같으면 블록 순서상 뒤의 블록
  const chosen = candidates.reduce<AgentNode | undefined>((best, agent) => (
    !best || (levels.get(agent.id) ?? -1) >= (levels.get(best.id) ?? -1) ? agent : best
  ), undefined)
  if (chosen) next.find((agent) => agent.id === chosen.id)!.final = true

  const reasons: Record<string, AutoFlagReasons> = {}
  for (const agent of next) {
    const needsFile: FlagExplanation = agent.needs_file_manual
      ? { manual: true, reason: agent.needs_file ? '직접 지정: 실행할 때 파일이 필요합니다.' : '직접 지정: 파일 없이 실행 프롬프트나 앞 단계 결과로 실행합니다.' }
      : agent.needs_file_hint ? { manual: false, reason: '생성기가 사용자 파일을 직접 읽는 블록으로 정했습니다.' }
        : !hasParent.has(agent.id) ? { manual: false, reason: '들어오는 연결이 없어 파일이 필요합니다.' }
          : { manual: false, reason: '앞 단계 결과를 입력으로 받습니다.' }
    let final: FlagExplanation
    if (agent.final_manual) final = { manual: true, reason: agent.final ? '직접 최종 블록으로 지정했습니다.' : '직접 최종 블록에서 뺐습니다.' }
    else if (manualFinal) final = { manual: false, reason: `'${manualFinal.name}' 블록을 직접 최종 블록으로 지정했습니다.` }
    else if (chosen?.id === agent.id) {
      final = { manual: false, reason: hinted.length ? '생성기가 최종 블록으로 정했습니다.'
        : sinks.length > 1 ? `끝나는 블록 ${sinks.length}개 중 가장 뒤 단계 블록이라 최종 블록으로 정했습니다.`
          : '끝나는 블록이라 최종 블록으로 정했습니다.' }
    } else if (!hasChild.has(agent.id)) final = { manual: false, reason: chosen ? `'${chosen.name}' 블록이 최종 블록으로 정해졌습니다.` : '최종 블록을 정할 수 없습니다.' }
    else final = { manual: false, reason: '뒤에 이어지는 블록이 있어 최종 블록이 아닙니다.' }
    reasons[agent.id] = { needsFile, final }
  }
  return { agents: next, reasons }
}

/** 작업 상태. 색만으로 구분하지 않도록 아이콘과 이름을 함께 쓴다. */
export const TASK_STATUS: Record<string, { label: string; icon: string }> = {
  blocked: { label: '선행 대기', icon: '⏸' },
  ready: { label: '워커 대기', icon: '◷' },
  running: { label: '실행 중', icon: '▶' },
  done: { label: '완료', icon: '✓' },
  failed: { label: '실패', icon: '✕' },
}

export function taskStatus(status: string) {
  return TASK_STATUS[status] ?? { label: status, icon: '•' }
}

export function formatDuration(ms: number) {
  const seconds = Math.max(0, Math.round(ms / 1000))
  if (seconds < 60) return `${seconds}초`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}분 ${seconds % 60}초`
  return `${Math.floor(minutes / 60)}시간 ${minutes % 60}분`
}

export function formatClock(value: string | null | undefined) {
  return value ? new Date(value).toLocaleTimeString() : '—'
}

/** 실행 중이면 지금까지 걸린 시간을 보여준다 */
export function taskDuration(task: Task, now: number) {
  if (!task.started_at) return '—'
  const end = task.finished_at ? new Date(task.finished_at).getTime() : now
  return formatDuration(end - new Date(task.started_at).getTime())
}

export function taskWorkerLabel(task: Task) {
  if (task.executor === 'cloud') return `클라우드 · ${PROVIDER_LABELS[task.provider ?? ''] ?? task.provider ?? '외부 API'}`
  if (task.assigned_device_id) return task.assigned_device_name ?? `삭제된 워커 #${task.assigned_device_id}`
  return task.status === 'blocked' ? '배정 전' : '배정 대기'
}

export const PROVIDER_LABELS: Record<string, string> = {
  ollama: 'Ollama',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
}

export const GENERATION_STAGE_LABELS: Record<string, string> = {
  connection: '연결 실패',
  parse: '응답 파싱 실패',
  validation: '구성 검증 실패',
}

/** 워크플로우 정보·실행 이력에 표시할 생성 모델 */
export function generationLabel(info: GenerationInfo | null | undefined) {
  if (!info) return '기록 없음 (이전 버전에서 생성)'
  if (info.source === 'fallback') return '기본 워크플로우 (규칙 기반)'
  const where = info.location === 'cloud' ? `외부 LLM API · ${PROVIDER_LABELS[info.provider ?? ''] ?? info.provider}` : '서버 로컬 LLM · Ollama'
  return `${where} · ${info.model}`
}

/** 실행 이력의 입력 파일을 한 줄로: "card_A.csv 외 2개" */
export function inputFilesSummary(records: RunInputRecord[] | null | undefined) {
  // 여러 슬롯이 같은 파일을 쓰면 한 번만 센다
  const names = [...new Map((records ?? []).flatMap((record) => record.files.map((file) => [file.id, file.name] as const))).values()]
  if (!names.length) return '입력 파일 없음'
  return names.length > 1 ? `${names[0]} 외 ${names.length - 1}개` : names[0]
}

/** "신용카드 거래 분류 에이전트" → "분류": 단계 요약에 쓰는 역할 단어 */
export function roleWord(name: string) {
  const words = name.replace(/에이전트$/, '').trim().split(/\s+/).filter(Boolean)
  return words[words.length - 1] || name
}

/** 같은 역할 단어를 묶어 "분류 3개 + 탐지"처럼 요약한다. */
export function stageSummary(names: string[]) {
  const counts = new Map<string, number>()
  names.forEach((name) => {
    const word = roleWord(name)
    counts.set(word, (counts.get(word) ?? 0) + 1)
  })
  return [...counts].map(([word, count]) => (count > 1 ? `${word} ${count}개` : word)).join(' + ')
}

export function issuesByNode(validation: ValidationResult | null | undefined) {
  const byNode = new Map<string, ValidationIssue[]>()
  for (const issue of [...(validation?.errors ?? []), ...(validation?.warnings ?? [])]) {
    for (const nodeId of issue.node_ids) byNode.set(nodeId, [...(byNode.get(nodeId) ?? []), issue])
  }
  return byNode
}

/** 실행 프롬프트를 넣어도 풀리지 않는 오류 */
export function blockingErrors(validation: ValidationResult | null | undefined) {
  return (validation?.errors ?? []).filter((issue) => !issue.resolvable_by_run_prompt)
}
