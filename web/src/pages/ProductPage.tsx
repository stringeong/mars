import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { PublicFooter, PublicHeader } from '../components/PublicChrome'

const steps = [
  { title: '하고 싶은 일을 적어요', text: '"카드 내역을 분류하고 이상 거래를 찾아 줘"처럼 평소 말하듯 한 문장이면 충분해요.' },
  { title: '만들어진 흐름을 확인해요', text: '역할별 에이전트와 실행 순서가 블록으로 그려져요. 연결을 바꾸거나 블록을 더해 직접 다듬을 수 있어요.' },
  { title: '내 기기들이 나눠서 실행해요', text: '동시에 할 수 있는 단계는 등록한 PC·노트북에 나눠 맡기고, 끝나면 결과를 한곳에 모아 보여줘요.' },
]

const features = [
  { title: '문장으로 만드는 워크플로우', text: '요청 한 줄로 에이전트 구성과 순서를 만들어요. 생성에 쓸 모델도 내 워커, 서버, 외부 API 중에서 골라요.' },
  { title: '눈으로 보며 고치는 편집기', text: '블록을 끌어 연결하고, 순환이나 빠진 입력처럼 실행할 수 없는 구성은 저장 전에 알려줘요.' },
  { title: '여러 기기로 나눠 실행', text: '같은 단계의 작업은 여러 워커가 동시에 처리해요. 연결이 끊긴 기기의 작업은 다른 기기가 이어받아요.' },
  { title: '로컬 우선, 필요할 때만 클라우드', text: '기본은 내 기기의 Ollama 모델로 처리하고, 더 강한 모델이 필요한 단계만 외부 API로 보낼 수 있어요.' },
  { title: '진행 상황 한눈에', text: '에이전트마다 어느 기기에서 언제 시작해 얼마나 걸렸는지 단계별 화면과 타임라인으로 보여줘요.' },
  { title: '한 번 만들고 계속 쓰기', text: '저장한 워크플로우는 입력 파일만 바꿔 다시 실행하거나, 복제해서 다른 용도로 고쳐 쓸 수 있어요.' },
]

const privacy = [
  { title: '허용한 폴더만 읽어요', text: '워커는 워크플로우에 연결한 폴더 밖의 파일에 접근하지 않아요.' },
  { title: '공유 폴더 파일은 기기 안에서만', text: '공유 디렉터리의 파일은 그 기기에서만 읽히고, 업로드한 파일만 서버를 거쳐 내 워커로 전달돼요.' },
  { title: '외부 전송은 실행 전에 확인', text: '외부 API로 보내는 단계가 있으면 무엇이 어디로 가는지 보여주고 동의를 받은 뒤 실행해요.' },
  { title: '포트를 열지 않아요', text: '워커가 서버에 먼저 연락해 일을 가져가는 방식이라 공유기 설정이나 포트 개방이 필요 없어요.' },
]

// 이 제품이 잘 맞는 이유: 나눠서 동시에 / 밖으로 보내기 싫은 자료 / 입력만 바뀌는 반복 / 다른 모델로 한 번 더 확인
type Fit = '동시 처리' | '민감한 자료' | '반복 작업' | '교차 확인'
const EXAMPLE_GROUPS = ['전체', '생활', '업무', '공부', '개발'] as const
// featured: '전체'에서 먼저 보여줄 예시 (여러 기기·기기 안 자료·교차 확인 같은 이 서비스의 강점이 잘 드러나는 것)
const examples: { group: typeof EXAMPLE_GROUPS[number]; title: string; prompt: string; fits: Fit[]; featured?: boolean }[] = [
  { group: '생활', title: '월간 가계부 분석', prompt: '신용카드·체크카드·계좌 내역을 분류하고 이번 달 지출 리포트로 정리해줘', fits: ['민감한 자료', '반복 작업'], featured: true },
  { group: '생활', title: '단체 대화방 정리', prompt: '단체 대화방 내보내기 파일에서 정해진 일정과 준비물만 뽑아줘', fits: ['민감한 자료'], featured: true },
  { group: '생활', title: '연말정산 의료비 정리', prompt: '병원·약국 영수증 파일에서 연말정산에 넣을 의료비 내역을 정리해줘', fits: ['민감한 자료', '반복 작업'] },
  { group: '생활', title: '여행 계획', prompt: '5명이 3박 4일로 다녀올 여행 일정과 예산을 짜줘', fits: ['동시 처리'] },
  { group: '생활', title: '건강 기록 돌아보기', prompt: '한 달 동안의 운동·수면 기록을 보고 패턴과 고칠 점을 알려줘', fits: ['민감한 자료', '반복 작업'] },
  { group: '업무', title: '계약서 만료일 정리', prompt: '공유 폴더의 계약서 PDF들에서 만료일과 자동 갱신 조항을 표로 정리해줘', fits: ['동시 처리', '민감한 자료'], featured: true },
  { group: '업무', title: '설문 주관식 분석', prompt: '설문 주관식 응답 1,000건을 주제별로 묶고 대표 의견을 뽑아줘', fits: ['동시 처리'], featured: true },
  { group: '업무', title: '과제 피드백 초안', prompt: '학생 과제 30개를 채점 기준표에 맞춰 1차 피드백 초안을 써줘', fits: ['동시 처리', '민감한 자료'], featured: true },
  { group: '업무', title: '문서 번역', prompt: '제품 설명서를 장별로 나눠 영어로 번역하고, 다른 모델로 용어와 어색한 문장을 확인해줘', fits: ['동시 처리', '교차 확인'], featured: true },
  { group: '업무', title: '매출 보고 요약', prompt: '매주 받는 매출 엑셀을 정리해 지난주와 비교한 보고용 요약을 만들어줘', fits: ['반복 작업', '민감한 자료'] },
  { group: '업무', title: '회의록 정리', prompt: '회의록을 읽고 결정 사항과 할 일을 담당자별로 정리해줘', fits: ['반복 작업'] },
  { group: '업무', title: '민원 분류', prompt: '접수된 민원 문장을 유형별로 나누고 핵심 키워드를 뽑아줘', fits: ['동시 처리', '민감한 자료'] },
  { group: '업무', title: '계약서 검토', prompt: '계약서 초안에서 불리한 조항과 빠진 항목을 찾아 검토 의견을 써줘', fits: ['민감한 자료', '교차 확인'] },
  { group: '업무', title: '고객 리뷰 분석', prompt: '상품 리뷰를 감정별로 나누고 자주 나오는 불만과 개선점을 정리해줘', fits: ['동시 처리', '반복 작업'] },
  { group: '업무', title: '주간 보고서', prompt: '이번 주 업무 메모들을 모아 팀 주간 보고서 형식으로 정리해줘', fits: ['반복 작업'] },
  { group: '공부', title: '논문 비교 요약', prompt: '논문 PDF 다섯 편을 각각 요약하고 공통점과 차이를 표로 비교해줘', fits: ['동시 처리'], featured: true },
  { group: '공부', title: '강의 자막 노트', prompt: '강의 자막 파일 10개를 각각 요약해 시험 대비 노트로 묶어줘', fits: ['동시 처리', '반복 작업'] },
  { group: '공부', title: '복습 문제 만들기', prompt: '강의 노트에서 핵심 개념을 정리하고 복습용 문제와 해설을 만들어줘', fits: ['반복 작업', '교차 확인'] },
  { group: '공부', title: '자기소개서 첨삭', prompt: '자기소개서를 문항별로 다듬고, 다른 모델로 한 번 더 읽어 어색한 곳을 짚어줘', fits: ['민감한 자료', '교차 확인'] },
  { group: '개발', title: '장애 보고서 초안', prompt: '에러 로그와 최근 변경 내역을 함께 보고 장애 원인 보고서 초안을 써줘', fits: ['민감한 자료', '교차 확인'], featured: true },
  { group: '개발', title: '로그 이상 탐지', prompt: '서버 로그를 구간별로 나눠 오류 패턴을 찾고 원인 후보를 정리해줘', fits: ['동시 처리', '민감한 자료'] },
  { group: '개발', title: '테스트 실패 묶기', prompt: '테스트 실패 로그 수십 개를 원인별로 묶고 먼저 고칠 순서를 정해줘', fits: ['동시 처리'] },
  { group: '개발', title: '코드 리뷰', prompt: '변경된 파일들을 나눠 검토하고 공통으로 보이는 문제를 리뷰 의견으로 모아줘', fits: ['동시 처리', '교차 확인'] },
]
const EXAMPLES_PREVIEW = 8

// 첫 화면 예시 화면에서 번갈아 보여줄 요청과, 그 요청으로 만들어지는 흐름(단계별 에이전트와 맡은 기기)
// 생성된 워크플로우의 블록: 역할 태그, 맡은 기기, 직접 받는 입력(파일·텍스트), 최종 블록 여부
type DemoBlock = { tag: string; name: string; device: string; input?: string; final?: boolean }
const DEMOS: { label: string; prompt: string; stages: DemoBlock[][] }[] = [
  {
    label: '가계부',
    prompt: '카드·계좌 내역으로 이번 달 어디에 돈을 많이 썼는지 리포트로 정리해줘',
    stages: [
      [{ tag: '분류', name: '카드 내역 분류', device: '데스크톱', input: '카드내역.csv' }, { tag: '분류', name: '계좌 내역 분류', device: '노트북', input: '계좌내역.csv' }],
      [{ tag: '분석', name: '지출 분석', device: '데스크톱' }],
      [{ tag: '작성', name: '리포트 작성', device: '노트북', final: true }],
    ],
  },
  {
    label: '회의록',
    prompt: '이번 주 회의록 세 개에서 결정 사항과 내가 할 일만 뽑아줘',
    stages: [
      [{ tag: '요약', name: '월요일 회의 요약', device: '데스크톱', input: '월요일.txt' }, { tag: '요약', name: '수요일 회의 요약', device: '노트북', input: '수요일.txt' }, { tag: '요약', name: '금요일 회의 요약', device: '데스크톱', input: '금요일.txt' }],
      [{ tag: '정리', name: '할 일 정리', device: '노트북', final: true }],
    ],
  },
  {
    label: '여행',
    prompt: '친구 4명이랑 부산 2박 3일, 맛집 위주로 일정이랑 1인당 예산 짜줘',
    stages: [
      [{ tag: '조사', name: '맛집 조사', device: '데스크톱', input: '텍스트 · 부산, 4명' }, { tag: '조사', name: '숙소 비교', device: '노트북', input: '텍스트 · 2박 3일' }],
      [{ tag: '계획', name: '일정 짜기', device: '데스크톱' }],
      [{ tag: '계산', name: '예산 계산', device: '노트북', final: true }],
    ],
  },
  {
    label: '리뷰',
    prompt: '우리 가게 리뷰 500개에서 손님들이 가장 많이 아쉬워한 점 5개만 알려줘',
    stages: [
      [{ tag: '분류', name: '리뷰 1~250번', device: '데스크톱', input: '리뷰.csv' }, { tag: '분류', name: '리뷰 251~500번', device: '노트북', input: '리뷰.csv' }],
      [{ tag: '분석', name: '불만 정리', device: '데스크톱' }],
      [{ tag: '작성', name: '개선 제안', device: '노트북', final: true }],
    ],
  },
]
const DEMO_INTERVAL = 4500

// 예시 화면의 생성 모델 선택. 실제 첫 화면처럼 내 워커·서버·외부 API 중에서 고른다 (서버 설정의 모델 목록 기준)
type GenLocation = 'worker' | 'local' | 'cloud'
type CloudProvider = 'openai' | 'anthropic' | 'gemini'
const GEN_WORKERS = ['데스크톱', '노트북']
const GEN_LOCAL_MODELS = { worker: ['qwen3:4b', 'gemma3:4b'], local: ['gemma3:4b', 'qwen3:4b'] }
const GEN_CLOUD: Record<CloudProvider, { name: string; models: string[] }> = {
  openai: { name: 'OpenAI', models: ['gpt-5-mini', 'gpt-5', 'gpt-4.1-mini'] },
  anthropic: { name: 'Anthropic', models: ['claude-sonnet-4-5', 'claude-haiku-3-5'] },
  gemini: { name: 'Gemini', models: ['gemini-3.8-flash', 'gemini-2.5-pro'] },
}

/** 제품 소개: 로그인하지 않은 사용자가 처음 보는 화면 */
export default function ProductPage() {
  const { hash } = useLocation()
  const [group, setGroup] = useState<typeof EXAMPLE_GROUPS[number]>('전체')
  const [showAllExamples, setShowAllExamples] = useState(false)
  // '전체'는 강점이 잘 드러나는 예시부터 보여주고 나머지는 더 보기로 연다
  const groupExamples = group === '전체'
    ? [...examples.filter((example) => example.featured), ...examples.filter((example) => !example.featured)]
    : examples.filter((example) => example.group === group)
  const shownExamples = group === '전체' && !showAllExamples ? groupExamples.slice(0, EXAMPLES_PREVIEW) : groupExamples
  // 예시 화면은 저절로 넘어가다가, 사용자가 예시를 고르면 멈춘다. 움직임 줄이기 설정이면 넘기지 않는다
  const [demoIndex, setDemoIndex] = useState(0)
  const [demoPinned, setDemoPinned] = useState(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)
  useEffect(() => {
    if (demoPinned) return
    const timer = window.setInterval(() => setDemoIndex((index) => (index + 1) % DEMOS.length), DEMO_INTERVAL)
    return () => window.clearInterval(timer)
  }, [demoPinned])
  const demo = DEMOS[demoIndex]
  const [genLocation, setGenLocation] = useState<GenLocation>('worker')
  const [genWorker, setGenWorker] = useState(GEN_WORKERS[0])
  const [genProvider, setGenProvider] = useState<CloudProvider>('openai')
  const genModels = genLocation === 'cloud' ? GEN_CLOUD[genProvider].models : GEN_LOCAL_MODELS[genLocation]
  const [genModel, setGenModel] = useState(GEN_LOCAL_MODELS.worker[0])
  const model = genModels.includes(genModel) ? genModel : genModels[0]
  const genHint = genLocation === 'worker' ? `${genWorker}의 Ollama가 만들어요. 요청은 내 기기에만 전달돼요.`
    : genLocation === 'local' ? '서버의 Ollama가 만들어요.'
      : `${GEN_CLOUD[genProvider].name} API가 만들어요. 요청이 외부로 전송된다는 안내를 확인한 뒤 진행해요.`
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
    else window.scrollTo(0, 0)
  }, [hash])

  return <div className="mk-page">
    <PublicHeader />

    <section className="mk-hero">
      <div className="mk-shell mk-hero-inner">
        <div className="mk-hero-copy">
          <span className="mk-kicker">멀티 에이전트 AI 워크플로우</span>
          <h1>가진 컴퓨터들로 꾸리는<br />나만의 AI 팀</h1>
          <p>하고 싶은 일을 문장으로 적으면 역할별 AI 에이전트가 짜이고, 집과 사무실의 PC·노트북이 나눠서 실행해요. 민감한 자료는 내 기기 밖으로 나가지 않아요.</p>
          <div className="mk-hero-actions">
            <Link className="mk-btn mk-btn-primary mk-btn-lg" to="/login?mode=register">회원가입</Link>
            <Link className="mk-btn mk-btn-light mk-btn-lg" to="/download">워커 다운로드</Link>
          </div>
          <small className="mk-hero-note">Windows · macOS · Linux · Ollama 로컬 모델</small>
        </div>
        <div className="mk-hero-visual">
          <div className="mk-window" aria-label="예시: 요청 한 문장과 그 요청으로 만들어지는 워크플로우">
            <div className="mk-window-bar" aria-hidden="true"><i /><i /><i /><span>marsflowlab.com</span></div>
            <div className="mk-composer">
              <strong>어떤 작업을 자동화할까요?</strong>
              <div className="mk-composer-box">
                <p key={demoIndex} className="mk-demo-text">{demo.prompt}</p>
                <div className="mk-composer-bar">
                  <div className="mk-gen" aria-label="생성 모델">
                    <select value={genLocation} onChange={(event) => { setGenLocation(event.target.value as GenLocation); setGenModel('') }} aria-label="실행 위치">
                      <option value="worker">내 워커</option>
                      <option value="local">서버 로컬</option>
                      <option value="cloud">외부 API</option>
                    </select>
                    {genLocation === 'worker' && <select value={genWorker} onChange={(event) => setGenWorker(event.target.value)} aria-label="워커">
                      {GEN_WORKERS.map((name) => <option key={name} value={name}>{name}</option>)}
                    </select>}
                    {genLocation === 'cloud' && <select value={genProvider} onChange={(event) => { setGenProvider(event.target.value as CloudProvider); setGenModel('') }} aria-label="제공자">
                      {(Object.keys(GEN_CLOUD) as CloudProvider[]).map((key) => <option key={key} value={key}>{GEN_CLOUD[key].name}</option>)}
                    </select>}
                    <select value={model} onChange={(event) => setGenModel(event.target.value)} aria-label="모델">
                      {genModels.map((name) => <option key={name} value={name}>{name}</option>)}
                    </select>
                  </div>
                  <b aria-hidden="true">↑</b>
                </div>
              </div>
              <small className="mk-gen-hint">{genHint}</small>
              <div className="mk-demo-chips" role="tablist" aria-label="예시 고르기">
                {DEMOS.map((item, index) => <button
                  key={item.label}
                  type="button"
                  role="tab"
                  aria-selected={index === demoIndex}
                  className={index === demoIndex ? 'active' : ''}
                  onClick={() => { setDemoIndex(index); setDemoPinned(true) }}
                >{item.label}</button>)}
              </div>
            </div>
            <div className="mk-canvas">
              <div className="mk-canvas-head">
                <span><b>생성된 워크플로우</b><small>블록 {demo.stages.flat().length}개 · {demo.stages.length}단계 · 구성 검사 통과</small></span>
                <span className="mk-canvas-actions" aria-hidden="true"><i>편집</i><i className="run">실행</i></span>
              </div>
              <div key={demoIndex} className="mk-canvas-body mk-demo-flow">
                {demo.stages.map((stage, index) => <div className="mk-canvas-step" key={index}>
                  {index > 0 && <i className="mk-canvas-arrow" aria-hidden="true">→</i>}
                  <div className="mk-canvas-col">
                    {stage.map((block) => <div key={block.name} className={`mk-block${block.final ? ' final' : ''}`}>
                      <span className="mk-block-tags"><em>{block.tag}</em>{block.final && <em className="final">최종</em>}</span>
                      <b>{block.name}</b>
                      <small>{block.device} · {genLocation === 'cloud' ? 'qwen3:4b' : model}</small>
                      {block.input && <span className="mk-block-input">{block.input.startsWith('텍스트') ? block.input : `파일 · ${block.input}`}</span>}
                    </div>)}
                  </div>
                </div>)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section className="mk-section mk-section-muted" id="how">
      <div className="mk-shell">
        <div className="mk-heading"><span className="mk-kicker">작동 방식</span><h2>요청부터 결과까지 세 단계</h2></div>
        <ol className="mk-steps">
          {steps.map((step, index) => <li key={step.title}>
            <span className="mk-step-no">{index + 1}</span>
            <h3>{step.title}</h3>
            <p>{step.text}</p>
          </li>)}
        </ol>
      </div>
    </section>

    <section className="mk-section" id="features">
      <div className="mk-shell">
        <div className="mk-heading"><span className="mk-kicker">기능</span><h2>혼자 쓰는 AI보다 한 단계 더</h2><p>여러 에이전트가 일을 나눠 맡고, 그 일을 내 기기들이 나눠 처리해요.</p></div>
        <div className="mk-features">
          {features.map((feature) => <article key={feature.title}><h3>{feature.title}</h3><p>{feature.text}</p></article>)}
        </div>
      </div>
    </section>

    <section className="mk-section mk-section-muted" id="privacy">
      <div className="mk-shell mk-split">
        <div className="mk-heading">
          <span className="mk-kicker">데이터 보호</span>
          <h2>자료는 정한 곳에만 머물러요</h2>
          <p>무엇을 어디서 처리할지 사용자가 정하고, 실행 전에 한 번 더 확인할 수 있어요.</p>
        </div>
        <div className="mk-privacy">
          {privacy.map((item) => <div key={item.title}><h3>{item.title}</h3><p>{item.text}</p></div>)}
        </div>
      </div>
    </section>

    <section className="mk-section" id="examples">
      <div className="mk-shell">
        <div className="mk-heading"><span className="mk-kicker">활용 예시</span><h2>이런 일을 맡겨 보세요</h2><p>입력만 바뀌는 반복 작업이나, 밖으로 보내기 싫은 자료를 다룰 때 특히 잘 맞아요.</p></div>
        <div className="mk-filter" role="tablist" aria-label="활용 분야">
          {EXAMPLE_GROUPS.map((name) => <button key={name} type="button" role="tab" aria-selected={group === name} className={group === name ? 'active' : ''} onClick={() => setGroup(name)}>{name}<small>{name === '전체' ? examples.length : examples.filter((example) => example.group === name).length}</small></button>)}
        </div>
        <div className="mk-examples">
          {shownExamples.map((example) => <div key={example.title}>
            <span className="mk-example-group">{example.group}</span>
            <b>{example.title}</b>
            <p>“{example.prompt}”</p>
            <div className="mk-fits">{example.fits.map((fit) => <small key={fit}>{fit}</small>)}</div>
          </div>)}
        </div>
        {shownExamples.length < groupExamples.length && <button type="button" className="mk-more" onClick={() => setShowAllExamples(true)}>예시 {groupExamples.length - shownExamples.length}개 더 보기</button>}
        <p className="mk-examples-note">질문 하나로 끝나는 일이나 최신 정보 검색은 일반 챗봇이 더 빨라요. 여러 단계로 나뉘는 일에서 차이가 커져요.</p>
      </div>
    </section>

    <section className="mk-cta">
      <div className="mk-shell mk-cta-inner">
        <div><h2>첫 워크플로우를 만들어 보세요</h2><p>워커를 설치해 기기를 연결하면 바로 시작할 수 있어요.</p></div>
        <div className="mk-hero-actions">
          <Link className="mk-btn mk-btn-light mk-btn-lg" to="/download">워커 다운로드</Link>
          <Link className="mk-btn mk-btn-outline mk-btn-lg" to="/login?mode=register">회원가입</Link>
        </div>
      </div>
    </section>

    <PublicFooter />
  </div>
}
