export interface BlockPreset {
  name: string
  role_prompt: string
  hint: string
}

export const BLOCK_PRESETS: BlockPreset[] = [
  {
    name: '정보 수집 에이전트',
    hint: '자료를 모아 정리',
    role_prompt:
      '당신은 정보 수집 담당입니다. 사용자의 요청과 제공된 자료를 바탕으로 필요한 정보를 항목별로 정리해 나열하세요.',
  },
  {
    name: '분석 에이전트',
    hint: '비교·분석해 인사이트 도출',
    role_prompt:
      '당신은 분석 담당입니다. 이전 단계의 결과를 비교·분석하고 핵심 인사이트를 도출하세요.',
  },
  {
    name: '검토 에이전트',
    hint: '오류·누락 점검',
    role_prompt:
      '당신은 검토 담당입니다. 이전 결과의 오류, 누락, 모순을 찾아 지적하고 구체적인 개선안을 제시하세요.',
  },
  {
    name: '요약·정리 에이전트',
    hint: '읽기 쉽게 통합 정리',
    role_prompt:
      '당신은 최종 정리 담당입니다. 앞선 결과들을 사용자가 읽기 쉬운 구조화된 형태로 통합·정리하세요.',
  },
  {
    name: '작성 에이전트',
    hint: '요청 형식으로 글쓰기',
    role_prompt:
      '당신은 글쓰기 담당입니다. 주어진 자료를 바탕으로 요청된 형식과 어조로 글을 작성하세요.',
  },
  {
    name: '빈 에이전트',
    hint: '직접 역할 정의',
    role_prompt: '',
  },
]
