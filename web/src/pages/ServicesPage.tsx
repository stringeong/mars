import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { CloudProvider, Device, GenerationError, GeneratorModels, Service } from '../types'
import { GENERATION_STAGE_LABELS, PROVIDER_LABELS } from '../workflow'

const suggestions = [
  { label: '자료 조사 보고서', text: '주제에 대한 믿을 만한 자료를 모으고 근거를 분석해서 간결한 조사 보고서로 정리해줘.' },
  { label: '문서 검토', text: '올린 문서를 읽고 핵심 쟁점과 위험 요소를 찾아 구조화된 검토 의견을 작성해줘.' },
  { label: '데이터 분석', text: '데이터를 분석해서 의미 있는 추세를 찾고 근거와 함께 의사결정 제안을 정리해줘.' },
]

/** 새 워크플로우: 대화형 앱처럼 입력창 하나로 시작한다. */
export default function ServicesPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [generatorModels, setGeneratorModels] = useState<GeneratorModels | null>(null)
  const [genLocation, setGenLocation] = useState<'local' | 'cloud'>('local')
  const [genProvider, setGenProvider] = useState<CloudProvider>('openai')
  const [genModel, setGenModel] = useState('')
  const [transferAck, setTransferAck] = useState(false)
  const [genError, setGenError] = useState<GenerationError | null>(null)
  const modelSelectRef = useRef<HTMLSelectElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.get<Device[]>('/devices').then(setDevices).catch(() => {})
    api.get<GeneratorModels>('/services/generator-models').then(setGeneratorModels).catch(() => {})
  }, [])

  // 외부 LLM API는 키를 등록한 제공자만 고를 수 있다
  const configuredCloud = (generatorModels?.cloud ?? []).filter((item) => item.configured)
  const selectedCloud = configuredCloud.find((item) => item.provider === genProvider)
  const genModelOptions = genLocation === 'cloud' ? selectedCloud?.models ?? [] : generatorModels?.local.models ?? []
  const genDefaultModel = genLocation === 'cloud' ? selectedCloud?.default_model : generatorModels?.local.default_model
  const online = devices.filter((device) => device.online).length
  const blockedByTransfer = genLocation === 'cloud' && (!transferAck || !selectedCloud)

  function chooseLocation(next: 'local' | 'cloud') {
    setGenLocation(next)
    setGenModel('')
    setTransferAck(false)
    if (next === 'cloud' && configuredCloud.length && !selectedCloud) setGenProvider(configuredCloud[0].provider)
  }

  // Enter는 생성, Shift+Enter는 줄바꿈. 한글 조합 중 Enter는 무시한다.
  function onPromptKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    formRef.current?.requestSubmit()
  }

  async function generate(e: FormEvent) {
    e.preventDefault()
    if (loading || blockedByTransfer) return
    setError('')
    setGenError(null)
    setLoading(true)
    try {
      const service = await api.post<Service>('/services/generate', {
        prompt,
        location: genLocation,
        provider: genLocation === 'cloud' ? genProvider : 'ollama',
        model: genModel,
        external_transfer_ack: genLocation === 'cloud' && transferAck,
      })
      navigate(`/services/${service.id}/setup`)
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail as { generation_error?: GenerationError } | undefined : undefined
      if (detail?.generation_error) setGenError(detail.generation_error)
      else setError(err instanceof Error ? err.message : '워크플로우를 만들지 못했어요.')
    } finally {
      setLoading(false)
    }
  }

  // 생성 실패 후 사용자가 고른 경우에만 규칙 기반 기본 워크플로우를 만든다
  async function chooseDefaultWorkflow() {
    if (!genError) return
    setLoading(true)
    try {
      const reason = `${GENERATION_STAGE_LABELS[genError.stage] ?? genError.stage} (${genError.model}): ${genError.message}`
      const service = await api.post<Service>('/services/generate', { prompt, use_fallback: true, fallback_reason: reason })
      navigate(`/services/${service.id}/setup`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '워크플로우를 만들지 못했어요.')
    } finally {
      setLoading(false)
    }
  }

  return <div className="home">
    <div className="home-center">
      <h1 className="home-title">어떤 작업을 자동화할까요?</h1>
      <p className="home-subtitle">하고 싶은 일을 적으면 에이전트 구성과 실행 순서를 만들어 드려요. 만든 뒤에도 자유롭게 고칠 수 있어요.</p>

      <form ref={formRef} className="home-composer" onSubmit={generate}>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          onKeyDown={onPromptKeyDown}
          placeholder="카드 사용 내역을 분류하고 이상 거래를 찾아 월간 리포트로 정리해줘"
          rows={3}
          required
          minLength={5}
          aria-label="만들고 싶은 워크플로우"
        />
        <div className="home-composer-bar">
          <div className="home-model" aria-label="생성 모델">
            <select value={genLocation} onChange={(event) => chooseLocation(event.target.value as 'local' | 'cloud')} aria-label="실행 위치">
              <option value="local">서버 로컬</option>
              <option value="cloud" disabled={!configuredCloud.length}>외부 API{configuredCloud.length ? '' : ' (키 없음)'}</option>
            </select>
            {genLocation === 'cloud' && <select value={genProvider} onChange={(event) => { setGenProvider(event.target.value as CloudProvider); setGenModel(''); setTransferAck(false) }} aria-label="제공자">
              {configuredCloud.map((item) => <option key={item.provider} value={item.provider}>{PROVIDER_LABELS[item.provider]}</option>)}
            </select>}
            <select ref={modelSelectRef} value={genModel} onChange={(event) => setGenModel(event.target.value)} aria-label="모델">
              <option value="">{genDefaultModel ?? '기본 모델'}</option>
              {genModelOptions.filter((model) => model !== genDefaultModel).map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
          </div>
          <span className={`home-workers${online ? ' online' : ''}`}>워커 {online}/{devices.length} 온라인</span>
          <button className="home-send" aria-label={loading ? '만드는 중' : '워크플로우 만들기'} disabled={loading || blockedByTransfer || prompt.trim().length < 5}>
            {loading ? <span className="home-spinner" aria-hidden="true" /> : <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>}
          </button>
        </div>
      </form>

      {loading && <p className="home-note">워크플로우를 만드는 중이에요. 모델에 따라 최대 30초쯤 걸려요.</p>}
      {genLocation === 'local' && generatorModels && !generatorModels.local.available && <p className="home-note warn">{generatorModels.local.error} 이대로 만들면 연결 실패로 안내돼요.</p>}
      {genLocation === 'cloud' && <label className="home-note home-ack">
        <input type="checkbox" checked={transferAck} onChange={(event) => setTransferAck(event.target.checked)} />
        생성 프롬프트가 {PROVIDER_LABELS[genProvider]} API로 전송되는 것을 확인했어요. API 키는 서버에만 보관되고, 업로드 파일은 이 단계에서 전송되지 않아요.
      </label>}

      {genError && <div className="home-failure" role="alert">
        <strong>{GENERATION_STAGE_LABELS[genError.stage] ?? genError.stage} · {genError.location === 'cloud' ? PROVIDER_LABELS[genError.provider] : '서버 로컬'} {genError.model}</strong>
        <p>{genError.message}</p>
        <div className="home-failure-actions">
          <button type="button" className="btn sm ghost" onClick={() => { setGenError(null); modelSelectRef.current?.focus() }}>다른 모델로 다시 시도</button>
          <button type="button" className="btn sm" disabled={loading} onClick={chooseDefaultWorkflow}>기본 워크플로우 사용</button>
        </div>
        <small>기본 워크플로우는 정보 수집 → 분석 → 정리 3단계이며, 생성 프롬프트는 서비스 목표로만 전달돼요.</small>
      </div>}
      {error && <p className="home-note error">{error}</p>}

      {!prompt && <div className="home-suggestions">
        {suggestions.map((item) => <button type="button" key={item.label} onClick={() => setPrompt(item.text)}>{item.label}</button>)}
      </div>}
    </div>
  </div>
}
