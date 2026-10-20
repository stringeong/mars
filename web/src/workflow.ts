import { GenerationInfo, ValidationIssue, ValidationResult } from './types'

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
