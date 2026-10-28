import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ExampleCard, PublicFooter, PublicHeader } from '../components/PublicChrome'
import DemoEditPanel from '../components/DemoEditPanel'
import RunPreview from '../components/RunPreview'
import WorkflowPreview from '../components/WorkflowPreview'
import { applyEdits, BlockEdit, blockId, DEMOS, initialEdit } from '../demos'
import { EXAMPLES } from '../examples'

const steps = [
  { title: '하고 싶은 일을 적어요', text: '"상담 기록에서 개인정보를 가리고 문의 유형을 분석해 줘"처럼 평소 말하듯 한 문장이면 충분해요.' },
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


// 첫 화면 예시 화면에서 번갈아 보여줄 요청과 그 흐름·실행 결과는 demos.ts에 있다
const DEMO_INTERVAL = 4500
const FEATURED_EXAMPLES = EXAMPLES.filter((example) => example.featured).slice(0, 4)

// 예시 화면의 생성 모델 선택. 실제 첫 화면처럼 내 워커·서버·외부 API 중에서 고른다 (서버 설정의 모델 목록 기준)
type GenLocation = 'worker' | 'local' | 'cloud'
type CloudProvider = 'openai' | 'anthropic' | 'gemini'
const GEN_WORKERS = ['데스크톱', '노트북', '회사 PC']
const GEN_LOCAL_MODELS = { worker: ['qwen3:4b', 'gemma3:4b'], local: ['gemma3:4b', 'qwen3:4b'] }
const GEN_CLOUD: Record<CloudProvider, { name: string; models: string[] }> = {
  openai: { name: 'OpenAI', models: ['gpt-5-mini', 'gpt-5', 'gpt-4.1-mini'] },
  anthropic: { name: 'Anthropic', models: ['claude-sonnet-4-5', 'claude-haiku-3-5'] },
  gemini: { name: 'Gemini', models: ['gemini-3.8-flash', 'gemini-2.5-pro'] },
}

/** 제품 소개: 로그인하지 않은 사용자가 처음 보는 화면 */
export default function ProductPage() {
  const { hash } = useLocation()
  // 예시 화면은 저절로 넘어가다가, 사용자가 예시를 고르면 멈춘다. 움직임 줄이기 설정이면 넘기지 않는다
  const [demoIndex, setDemoIndex] = useState(0)
  const [demoPinned, setDemoPinned] = useState(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)
  useEffect(() => {
    if (demoPinned) return
    const timer = window.setInterval(() => setDemoIndex((index) => (index + 1) % DEMOS.length), DEMO_INTERVAL)
    return () => window.clearInterval(timer)
  }, [demoPinned])
  // 편집 예시: 블록을 골라 실행 위치·워커·모델·첨부 파일을 바꾼다. 예시마다 따로 기억하고 실행 미리보기에도 쓴다
  const [editing, setEditing] = useState(false)
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null)
  const [edits, setEdits] = useState<Record<string, Record<string, BlockEdit>>>({})
  const demo = useMemo(() => applyEdits(DEMOS[demoIndex], edits[DEMOS[demoIndex].label]), [demoIndex, edits])
  // 실행 미리보기는 따로 고른 예시를 돌린다. 위에서 예시를 고르거나 '실행'을 누르면 그 예시로 맞춘다
  const [runIndex, setRunIndex] = useState(0)
  const [runKey, setRunKey] = useState(0)
  const runDemoData = useMemo(() => applyEdits(DEMOS[runIndex], edits[DEMOS[runIndex].label]), [runIndex, edits])
  function pickDemo(index: number) { setDemoIndex(index); setDemoPinned(true); setRunIndex(index); setSelectedBlock(editing ? blockId(0, 0) : null) }
  function runDemo() {
    setDemoPinned(true); setRunIndex(demoIndex); setRunKey((key) => key + 1); setEditing(false); setSelectedBlock(null)
    document.getElementById('run')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  function startEditing(id = blockId(0, 0)) { setDemoPinned(true); setEditing(true); setSelectedBlock(id) }
  const selectedPosition = selectedBlock?.match(/^s(\d+)-(\d+)$/)
  const originalBlock = selectedPosition ? DEMOS[demoIndex].stages[Number(selectedPosition[1])]?.[Number(selectedPosition[2])] : undefined
  const selectedEdit = originalBlock && selectedBlock ? edits[DEMOS[demoIndex].label]?.[selectedBlock] ?? initialEdit(originalBlock) : undefined
  function changeEdit(edit: BlockEdit) {
    if (!selectedBlock) return
    const label = DEMOS[demoIndex].label
    setEdits((current) => ({ ...current, [label]: { ...current[label], [selectedBlock]: edit } }))
  }
  function resetEdits() {
    const label = DEMOS[demoIndex].label
    setEdits((current) => { const next = { ...current }; delete next[label]; return next })
  }
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
                  onClick={() => pickDemo(index)}
                >{item.label}</button>)}
              </div>
            </div>
            <div className="mk-canvas">
              <div className="mk-canvas-head">
                <span><b>생성된 워크플로우</b><small>블록 {demo.stages.flat().length}개 · {demo.stages.length}단계 · 구성 검사 통과</small></span>
                <span className="mk-canvas-actions"><button type="button" className={`edit${editing ? ' active' : ''}`} aria-pressed={editing} onClick={() => (editing ? (setEditing(false), setSelectedBlock(null)) : startEditing())}>{editing ? '편집 완료' : '편집'}</button><button type="button" className="run" onClick={runDemo}>실행</button></span>
              </div>
              {/* 실제 편집기와 같은 블록·연결선으로 그린다. 실행 모델은 내 워커·서버 모델을 따르고, 외부 API로 생성해도 실행은 로컬 모델 기준 */}
              <div key={demoIndex} className="mk-demo-flow">
                <WorkflowPreview demo={demo} model={genLocation === 'cloud' ? 'qwen3:4b' : model} selectedId={editing ? selectedBlock : null} onSelect={(id) => startEditing(id)} />
              </div>
              {!editing && <p className="mk-edit-tip">블록을 누르거나 <b>편집</b>을 눌러 워커·모델·파일을 바꿔 보세요.</p>}
              {editing && originalBlock && selectedEdit && <DemoEditPanel block={originalBlock} edit={selectedEdit} onChange={changeEdit} onReset={resetEdits} onRun={runDemo} />}
            </div>
          </div>
        </div>
      </div>
    </section>

    <section className="mk-section mk-run-section" id="run">
      <div className="mk-shell">
        <div className="mk-heading">
          <span className="mk-kicker">실행 미리보기</span>
          <h2>실행하면 이렇게 진행돼요</h2>
          <p>같은 단계의 블록은 여러 기기가 동시에 맡아요. 진행률과 기기별 타임라인이 실시간으로 바뀌고, 마지막 블록이 끝나면 최종 결과가 나와요.</p>
        </div>
        <div className="mk-demo-chips mk-run-chips" role="tablist" aria-label="실행해 볼 예시">
          {DEMOS.map((item, index) => <button key={item.label} type="button" role="tab" aria-selected={index === runIndex} className={index === runIndex ? 'active' : ''} onClick={() => setRunIndex(index)}>{item.label}</button>)}
        </div>
        <RunPreview demo={runDemoData} runKey={runKey} />
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
        <div className="mk-examples">
          {FEATURED_EXAMPLES.map((example) => <ExampleCard key={example.title} example={example} />)}
        </div>
        <Link className="mk-more" to="/examples">활용 예시 {EXAMPLES.length}개 모두 보기 →</Link>
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
