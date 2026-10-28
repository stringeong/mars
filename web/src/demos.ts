/** 제품 소개 첫 화면의 예시: 요청 한 문장, 그 요청으로 만들어지는 흐름, 실행하면 나오는 결과.
 *  이 서비스의 강점이 드러나는 일로 고른다: 기기 안에서 가리기(마스킹), 여러 기기로 나눠 동시에 처리하기,
 *  다른 모델로 교차 확인 */

// 생성된 워크플로우의 블록: 역할 태그, 맡은 기기, 직접 받는 입력(파일·디렉터리·텍스트), 최종 블록 여부
// model: 이 블록만 다른 모델을 쓸 때. cloud: 외부 API로 보내는 블록(맡은 기기 대신 제공자에게 간다)
// secs·output은 실행 미리보기용: 이 블록이 걸리는 시간(초)과 끝났을 때 보이는 출력
export type DemoBlock = {
  tag: string
  name: string
  device: string
  input?: string
  final?: boolean
  model?: string
  cloud?: { provider: CloudProvider; model: string }
  // 편집 예시에서 바꾼 값: 워커 자동 배정 여부, 첨부 파일 목록(있으면 input 대신 보여준다)
  autoWorker?: boolean
  files?: string[]
  secs: number
  output: string
}
export type CloudProvider = 'openai' | 'anthropic' | 'gemini'
export type Demo = { label: string; prompt: string; stages: DemoBlock[][]; result: string }

export const DEMOS: Demo[] = [
  {
    label: '개인정보 마스킹',
    prompt: '고객 상담 기록 1,000건에서 이름·전화번호·카드번호를 가리고, 가린 본문만 외부 AI로 보내 문의 유형을 분석해줘',
    stages: [
      [
        { tag: '마스킹', name: '상담 앞 500건 가리기', device: '데스크톱', input: '상담기록_1.csv', secs: 22, output: '이름 412개, 전화번호 388개, 카드번호 61개를 [이름]·[전화]·[카드]로 바꿨어요.\n원문은 이 기기 밖으로 나가지 않았어요.' },
        { tag: '마스킹', name: '상담 뒤 500건 가리기', device: '노트북', input: '상담기록_2.csv', secs: 20, output: '이름 397개, 전화번호 402개, 주소 75개를 가렸어요.\n가린 본문만 다음 단계로 넘겨요.' },
      ],
      [{ tag: '분석', name: '문의 유형 분석', device: '외부 API', cloud: { provider: 'openai', model: 'gpt-5-mini' }, secs: 14, output: '가린 본문 1,000건만 OpenAI로 보냈어요 (실행 전에 전송 동의 확인).\n배송 지연 31% · 환불 24% · 결제 오류 17% · 회원 정보 12% · 기타 16%' }],
      [{ tag: '작성', name: '리포트 작성', device: '노트북', final: true, secs: 12, output: '유형별 비중, 대표 문의, 개선 제안을 묶어 리포트로 정리했어요.' }],
    ],
    result: `# 고객 문의 유형 분석 (10월 · 1,000건)

개인정보 1,735개를 내 기기에서 가린 뒤 분석했어요.
외부 API에는 가린 본문만 전송됐어요.

## 문의 유형
1. 배송 지연 — 312건 (31%)
2. 환불 요청 — 238건 (24%)
3. 결제 오류 — 171건 (17%)
4. 회원 정보 변경 — 118건 (12%)
5. 기타 — 161건 (16%)

## 대표 문의 (가린 본문)
- "[이름]입니다. 주문한 지 5일째인데 아직 출고 전이라고 나와요"
- "[카드]로 결제가 두 번 됐어요. 하나 취소해 주세요"

## 제안
- 출고가 늦어지면 자동 안내 문자 보내기 → 배송 문의 약 30% 감소 예상
- 중복 결제를 자동으로 찾아 바로 취소`,
  },
  {
    label: '회의록 분석',
    prompt: '캡스톤 팀 회의록 세 개를 나눠 요약하고, 결정 사항과 팀원별 할 일을 중간 발표 전까지 마감일 순으로 정리해줘',
    stages: [
      [
        { tag: '요약', name: '주제 확정 회의 요약', device: '데스크톱', input: '0930_1차회의.txt', secs: 16, output: '결정 2건: 주제를 "교내 셔틀 혼잡도 알림 앱"으로 확정, 중간 발표는 시연 영상으로 대체.\n할 일 1건: 경쟁 앱 3개 비교표(최유진, 11/6).' },
        { tag: '요약', name: '역할 분담 회의 요약', device: '노트북', input: '1007_역할분담.txt', secs: 14, output: '결정 1건: 서버 김민수 · 앱 이서연·박지훈 · 설문·디자인 최유진.\n할 일 3건: 사용자 설문 50명 이상(최유진, 11/2), API 명세서(김민수, 11/3), 앱 화면 설계(이서연, 11/5).' },
        { tag: '요약', name: '중간 점검 회의 요약', device: '연구실 PC', input: '1014_중간점검.txt', secs: 15, output: '결정 1건: 셔틀 위치는 학교 API 대신 직접 수집하기로 변경.\n할 일 3건: GPS 수집 테스트(박지훈, 11/7), 발표 슬라이드(김민수, 11/10), 시연 영상(이서연·박지훈, 11/11).' },
      ],
      [{ tag: '정리', name: '팀원별 할 일 정리', device: '노트북', final: true, secs: 14, output: '세 회의의 결정 사항 4건과 할 일 7건을 중간 발표(11/12) 기준 마감일 순으로 모았어요.' }],
    ],
    result: `# 캡스톤 팀 회의 정리 (회의 3건 · 중간 발표 11/12)

## 결정 사항
- 주제 확정: 교내 셔틀 혼잡도 알림 앱 (9/30)
- 중간 발표는 시연 영상으로 대체 (9/30)
- 역할 분담: 서버 김민수 · 앱 이서연·박지훈 · 설문·디자인 최유진 (10/7)
- 셔틀 위치 데이터는 직접 수집으로 변경 (10/14)

## 팀원별 할 일 (마감일 순)
- 최유진 — 사용자 설문 배포, 50명 이상 · 11/2
- 김민수 — API 명세서 작성 · 11/3
- 이서연 — 앱 화면 설계 · 11/5
- 최유진 — 경쟁 앱 3개 비교표 · 11/6
- 박지훈 — GPS 수집 테스트 · 11/7
- 김민수 — 중간 발표 슬라이드 · 11/10
- 이서연·박지훈 — 시연 영상 촬영 · 11/11

## 다음 회의 안건
- 직접 수집한 위치 데이터에서 개인정보를 어떻게 가릴지 정하기`,
  },
  {
    label: '교차 확인 번역',
    prompt: '졸업 논문 국문 초록을 영어로 번역하고, 번역에 쓰지 않은 다른 모델로 용어와 문법을 한 번 더 확인해줘',
    stages: [
      [
        { tag: '번역', name: '초록 초벌 번역', device: '데스크톱', input: '초록_국문.docx', secs: 20, output: 'This study suggests a model which predicts the hourly passenger of school shuttle bus by using class timetable, weather and past boarding record. We collected 41,200 boarding records of two routes during one semester and combined with lecture start and end time. Gradient boosting model reduced mean absolute error 18% compared to moving average, and especially the improvement was big in 10 minutes before morning class. Through this, we suggest to add one bus at 8:40 and 10:40 on Monday and Wednesday. This method only uses the data which university already has, so it can be applied to other campus with small cost.' },
        { tag: '용어', name: '전공 용어집 만들기', device: '노트북', input: '초록_국문.docx', secs: 14, output: '초록에서 전공 용어 8개를 뽑아 영어 표기를 정했어요.\n탑승 수요 → ridership · 셔틀버스 → campus shuttle · 강의 시간표 → class timetable\n이동평균 → moving-average baseline · 평균절대오차 → mean absolute error (MAE)\n그래디언트 부스팅 → gradient-boosted tree · 노선 → route · 학기 → semester' },
      ],
      [{ tag: '검수', name: '다른 모델로 교차 확인', device: '연구실 PC', model: 'gemma3:12b', secs: 18, output: '번역에 쓰지 않은 모델(gemma3:12b)로 원문·초벌 번역·용어집을 함께 읽었어요.\n용어 불일치 3곳, 문법 4곳, 어색한 직역 2곳을 고치자고 제안했어요.\n예) "the hourly passenger" → "the hourly ridership", "Through this," → "Based on these predictions,"' }],
      [{ tag: '정리', name: '최종 번역본 정리', device: '데스크톱', final: true, secs: 12, output: '검수 의견 9곳을 반영해 최종 번역본과 수정 내역을 만들었어요.' }],
    ],
    result: `# Abstract (최종 번역본)

This study proposes a model that predicts the hourly ridership of campus shuttle buses from class timetables, weather, and past boarding records. We collected 41,200 boarding records from two campus routes over one semester and combined them with lecture start and end times. A gradient-boosted tree model reduced the mean absolute error (MAE) by 18% compared with a moving-average baseline, with the largest gains in the ten minutes before morning classes. Based on these predictions, we recommend adding one bus at 8:40 and 10:40 on Mondays and Wednesdays. Because the approach relies only on data that universities already hold, it can be applied to other campuses at little additional cost.

Keywords: campus shuttle, ridership forecasting, gradient-boosted tree, class timetable

## 교차 확인에서 고친 곳 (gemma3:12b · 9곳)
- 용어 통일 3곳: passenger / boarding demand → ridership, gradient boosting model → gradient-boosted tree, moving average → moving-average baseline
- 문법 4곳: "the hourly passenger" → "the hourly ridership", 관사 누락 3곳 (a model, the mean absolute error, other campuses)
- 직역 표현 2곳: "by using" → "from", "Through this," → "Based on these predictions,"`,
  },
  {
    label: '로그 나눠 분석',
    prompt: '서버 로그 3일치를 기기별로 나눠 오류 패턴을 찾고, 토큰·IP는 가린 채 장애 보고서 초안을 써줘',
    stages: [
      [
        { tag: '분석', name: '10/27 로그 분석', device: '데스크톱', input: 'app-1027.log', secs: 20, output: '오류 1,204건 · 타임아웃 71%.\n14:02부터 DB 연결 대기 시간이 늘기 시작했어요.' },
        { tag: '분석', name: '10/28 로그 분석', device: '노트북', input: 'app-1028.log', secs: 18, output: '오류 3,877건 · 14:05~14:41에 결제 API 502가 몰렸어요.' },
        { tag: '분석', name: '10/29 로그 분석', device: '회사 PC', input: 'app-1029.log', secs: 19, output: '오류 412건 · v2.8.1 배포 이후 정상으로 돌아왔어요.' },
      ],
      [{ tag: '작성', name: '장애 보고서 초안', device: '데스크톱', final: true, secs: 16, output: '세 날짜의 결과를 시간순으로 맞추고, 로그 속 토큰·IP 58개를 가렸어요.' }],
    ],
    result: `# 장애 보고서 초안 — 10/28 결제 API 502 오류

## 요약
- 영향: 10/28 14:05~14:41 (36분), 결제 실패 약 3,100건
- 원인 후보: DB 연결 풀 고갈 → 결제 API 응답 지연 → 게이트웨이 502
- 조치: v2.8.1 배포로 연결 풀 20 → 60, 10/29부터 정상

## 타임라인
- 10/27 14:02 DB 연결 대기 증가 (전조)
- 10/28 14:05 결제 API 502 급증
- 10/28 14:41 연결 풀 수동 재시작 후 회복
- 10/29 09:30 v2.8.1 배포

로그 속 토큰·IP 58개는 [토큰]·[IP]로 가렸어요.`,
  },
]

// ---------- 편집 예시 ----------
// 편집 화면처럼 블록마다 실행 위치·워커·모델·첨부 파일을 바꿔 볼 수 있다. 바꾼 값은 실행 미리보기에도 쓰인다.
export const DEMO_WORKERS = ['데스크톱', '노트북', '연구실 PC', '회사 PC']
export const DEMO_LOCAL_MODELS = ['qwen3:4b', 'gemma3:4b', 'gemma3:12b', 'llama3.1:8b']
export const DEMO_DEFAULT_MODEL = 'qwen3:4b'
export const DEMO_CLOUD: Record<CloudProvider, { name: string; models: string[] }> = {
  // 서버 설정(PROVIDER_MODELS)의 목록과 같게 둔다
  openai: { name: 'OpenAI', models: ['gpt-5-mini', 'gpt-5', 'gpt-4.1-mini'] },
  anthropic: { name: 'Anthropic', models: ['claude-sonnet-4-5', 'claude-haiku-3-5'] },
  gemini: { name: 'Google Gemini', models: ['gemini-3.8-flash', 'gemini-2.5-pro'] },
}

export type DemoFile = { name: string; size: number }
// location: 'ollama'은 내 워커, 나머지는 외부 API. worker가 빈 문자열이면 자동 배정, model이 비면 기본 모델
export type BlockEdit = { location: 'ollama' | CloudProvider; worker: string; model: string; files: DemoFile[] }

export const blockId = (column: number, row: number) => `s${column}-${row}`

// 예시 파일 크기는 이름으로 정해 두어 다시 그려도 바뀌지 않게 한다
const fakeSize = (name: string) => 18_000 + [...name].reduce((sum, char) => sum + char.charCodeAt(0) * 37, 0) % 240_000

/** 블록의 처음 설정. 디렉터리·텍스트 입력은 파일이 아니므로 첨부 파일에 넣지 않는다 */
export function initialEdit(block: DemoBlock): BlockEdit {
  const file = block.input && !/^(텍스트|디렉터리)/.test(block.input) ? [{ name: block.input, size: fakeSize(block.input) }] : []
  return block.cloud
    ? { location: block.cloud.provider, worker: '', model: block.cloud.model, files: file }
    : { location: 'ollama', worker: block.device, model: block.model ?? '', files: file }
}

/** 편집한 값을 반영한 예시. 바꾼 블록이 없으면 원래 예시를 그대로 돌려준다 */
export function applyEdits(demo: Demo, edits: Record<string, BlockEdit> | undefined): Demo {
  if (!edits || !Object.keys(edits).length) return demo
  return {
    ...demo,
    stages: demo.stages.map((stage, column) => stage.map((block, row) => {
      const edit = edits[blockId(column, row)]
      if (!edit) return block
      const keptInput = block.input && /^(텍스트|디렉터리)/.test(block.input) ? block.input : undefined
      const base = { ...block, input: keptInput, files: edit.files.map((file) => file.name) }
      if (edit.location !== 'ollama') {
        return { ...base, cloud: { provider: edit.location, model: edit.model || DEMO_CLOUD[edit.location].models[0] }, model: undefined, autoWorker: false, device: '외부 API' }
      }
      return { ...base, cloud: undefined, model: edit.model || undefined, autoWorker: !edit.worker, device: edit.worker || (block.cloud ? DEMO_WORKERS[0] : block.device) }
    })),
  }
}
