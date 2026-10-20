import { GenerationInfo, RunInputRecord, Task, ValidationIssue, ValidationResult } from './types'

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
