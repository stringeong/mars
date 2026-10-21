import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import ValidationPanel from '../components/ValidationPanel'
import { AgentNode, Execution, ExecutionListItem, InputReview, InputReviewBlock, RunInputRecord, Service, UploadedFile, ValidationResult, WorkflowNode } from '../types'
import { blockInputs, formatBytes, generationLabel, PROVIDER_LABELS } from '../workflow'

type Transfer = { node_id: string; node_name: string; provider: string; type: 'user_input' | 'text_input' | 'derived_text' | 'file_text'; file_ids?: number[]; sources?: string[] }
type Preview = { requires_consent: boolean; consent_token: string | null; transfers: Transfer[]; validation: ValidationResult; review: InputReview }
type RunInputs = { slots: Record<string, number[]>; nodes: Record<string, number[]> }
type InputEntry = { kind: 'slot' | 'node'; id: string; label: string; format?: string; blocks: string[]; directories: number[]; defaults: number[] }

const isAgent = (node: WorkflowNode): node is AgentNode => !node.type || node.type === 'agent'
const sameIds = (a: number[], b: number[]) => a.length === b.length && a.every((value, index) => value === b[index])

const providerName = (provider: string | null) => (provider && PROVIDER_LABELS[provider as keyof typeof PROVIDER_LABELS]) || provider || '외부 API'

/** 블록이 실행되는 곳. 업로드 파일은 서버를 거쳐 이곳으로 전달된다. */
function destination(block: InputReviewBlock) {
  if (block.executor === 'cloud') return `외부 API · ${providerName(block.provider)}`
  return block.device_name ? `워커 · ${block.device_name}` : '워커 · 실행할 때 자동 배정'
}

/**
 * 실행 화면: 이번 실행의 입력 파일을 고른다. 블록별 텍스트 데이터·'입력 없이 실행 허용'은 편집 화면에서 정하고,
 * 실행 직전 확인 창에서 이번 실행에 쓰이는 입력(나가는 파일·텍스트)을 한 번에 보여준다.
 */
export default function WorkflowRunPage() {
  const { id } = useParams()
  const [searchParams] = useSearchParams()
  const fromExecution = searchParams.get('from')
  const navigate = useNavigate()
  const [service, setService] = useState<Service | null>(null)
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [inputs, setInputs] = useState<RunInputs>({ slots: {}, nodes: {} })
  const [prefillSource, setPrefillSource] = useState('워크플로우 기본값')
  const [droppedFiles, setDroppedFiles] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [acknowledged, setAcknowledged] = useState(false)
  const [uploadTarget, setUploadTarget] = useState<InputEntry | null>(null)
  const uploadRef = useRef<HTMLInputElement>(null)

  const entries = useMemo<InputEntry[]>(() => {
    if (!service) return []
    const agents = service.graph.nodes.filter(isAgent)
    const slotEntries = (service.graph.input_slots ?? []).map((slot) => ({
      kind: 'slot' as const,
      id: slot.id,
      label: slot.description || '사용자 파일',
      format: slot.format,
      blocks: agents.filter((agent) => (agent.input_slot_ids ?? []).includes(slot.id)).map((agent) => agent.name),
      directories: slot.directory_ids,
      defaults: slot.file_ids,
    }))
    // 슬롯 없이 블록에 직접 파일을 붙인 이전 버전 워크플로우
    const nodeEntries = agents
      .filter((agent) => (agent.uploaded_file_ids ?? []).length || (agent.needs_file && !(agent.input_slot_ids ?? []).length))
      .map((agent) => ({ kind: 'node' as const, id: agent.id, label: agent.name, blocks: [agent.name], directories: [], defaults: agent.uploaded_file_ids ?? [] }))
    return [...slotEntries, ...nodeEntries]
  }, [service])

  // 시작 블록과 텍스트 데이터를 받는 블록 (파일 외 입력을 실행 전에 보여준다)
  const blockEntries = useMemo(() => {
    if (!service) return []
    const targets = new Set(service.graph.edges.filter((edge) => (edge.relation ?? 'workflow') === 'workflow').map((edge) => edge.target))
    const slots = service.graph.input_slots ?? []
    return service.graph.nodes.filter(isAgent)
      .map((agent) => ({ agent, isStart: !targets.has(agent.id), inputs: blockInputs(agent, slots, !targets.has(agent.id)) }))
      .filter(({ isStart, inputs }) => isStart || inputs.hasText)
  }, [service])

  useEffect(() => {
    async function load() {
      try {
        const [loaded, loadedFiles] = await Promise.all([api.get<Service>(`/services/${id}`), api.get<UploadedFile[]>('/files')])
        setService(loaded)
        setFiles(loadedFiles)
        // 지정한 실행(다시 실행) 또는 이 워크플로우의 가장 최근 실행 값으로 입력 파일을 미리 채운다
        let previous: { id: number; input_files?: RunInputRecord[] | null } | undefined
        if (fromExecution) previous = await api.get<Execution>(`/executions/${fromExecution}`).catch(() => undefined)
        else previous = (await api.get<ExecutionListItem[]>(`/executions?service_id=${id}`).catch(() => []))[0]
        const existing = new Set(loadedFiles.map((file) => file.id))
        const next: RunInputs = { slots: {}, nodes: {} }
        let dropped = 0
        for (const record of previous?.input_files ?? []) {
          // 텍스트 데이터는 실행마다 바꾸지 않고 워크플로우에 저장된 값을 쓴다
          if (record.kind === 'text') continue
          const ids = record.files.map((file) => file.id)
          const kept = ids.filter((fileId) => existing.has(fileId))
          dropped += ids.length - kept.length
          if (record.kind === 'slot') next.slots[record.id] = kept
          else next.nodes[record.id] = kept
        }
        setInputs(next)
        setDroppedFiles(dropped)
        if (previous?.input_files?.some((record) => record.kind !== 'text')) setPrefillSource(`이전 실행 #${previous.id} 값`)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Unable to load workflow.')
      }
    }
    load()
  }, [id, fromExecution])

  function selected(entry: InputEntry) {
    const bucket = entry.kind === 'slot' ? inputs.slots : inputs.nodes
    return bucket[entry.id] ?? entry.defaults
  }

  function setSelected(entry: InputEntry, fileIds: number[]) {
    const key = entry.kind === 'slot' ? 'slots' : 'nodes'
    setInputs((current) => ({ ...current, [key]: { ...current[key], [entry.id]: [...new Set(fileIds)] } }))
    setValidation(null)
    setAcknowledged(false)
  }

  // 화면의 모든 입력 칸을 보낸다. 미리보기와 실행에 같은 값을 보내야 외부 전송 동의가 맞물린다.
  function payloadInputs(): RunInputs {
    const payload: RunInputs = { slots: {}, nodes: {} }
    entries.forEach((entry) => { payload[entry.kind === 'slot' ? 'slots' : 'nodes'][entry.id] = selected(entry) })
    return payload
  }

  function showValidationFrom(cause: unknown) {
    const detail = cause instanceof ApiError ? cause.detail as { validation?: ValidationResult } | undefined : undefined
    if (detail?.validation) setValidation(detail.validation)
  }

  async function start(consentToken?: string | null) {
    setLoading(true)
    setError('')
    try {
      const execution = await api.post<Execution>(`/services/${id}/executions`, { input_files: payloadInputs(), consent_token: consentToken || null, acknowledge_warnings: acknowledged })
      navigate(`/executions/${execution.id}`)
    } catch (cause) {
      setPreview(null)
      showValidationFrom(cause)
      setError(cause instanceof Error ? cause.message : 'Unable to start workflow.')
    } finally {
      setLoading(false)
    }
  }

  // 실행을 누르면 검사하고, 오류가 없으면 이번 실행에 쓰이는 입력을 확인 창으로 보여준다
  async function run(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const result = await api.post<Preview>(`/services/${id}/executions/preview`, { input_files: payloadInputs() })
      setValidation(result.validation)
      if (result.validation.errors.length) { setError('구성 오류를 고친 뒤 실행할 수 있습니다.'); return }
      setAcknowledged(false)
      setPreview(result)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to inspect workflow.')
    } finally {
      setLoading(false)
    }
  }

  function startUpload(entry: InputEntry) {
    setUploadTarget(entry)
    uploadRef.current?.click()
  }

  async function onUpload(event: ChangeEvent<HTMLInputElement>) {
    const entry = uploadTarget
    const picked = event.target.files
    if (!entry || !picked?.length) return
    setLoading(true)
    try {
      const uploaded: UploadedFile[] = []
      for (const file of Array.from(picked)) {
        const form = new FormData()
        form.append('file', file)
        uploaded.push(await api.upload<UploadedFile>('/files', form))
      }
      setFiles((current) => [...uploaded, ...current])
      setSelected(entry, [...selected(entry), ...uploaded.map((file) => file.id)])
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '파일 업로드 실패')
    } finally {
      setLoading(false)
      setUploadTarget(null)
      event.target.value = ''
    }
  }

  async function duplicate() {
    try {
      const copy = await api.post<Service>(`/services/${id}/duplicate`)
      navigate(`/services/${copy.id}/setup`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '복제 실패')
    }
  }

  if (!service) return <div className="page-loading">{error || 'Loading workflow...'}</div>
  const fileName = (fileId: number) => files.find((file) => file.id === fileId)?.original_name || `File #${fileId}`

  return <div className="workflow-run-page">
    <header className="page-topbar"><div><div className="breadcrumb">M.A.R.S <span>/</span> Workflows <span>/</span> {service.name} <span>/</span> Run</div><h1>Configure execution</h1><p>이번 실행에 쓸 입력 파일을 확인하고, 필요하면 바꾼 뒤 저장된 워크플로우를 실행합니다.</p></div><div className="builder-header-actions"><Link className="btn ghost" to={`/services/${service.id}/setup`}>설정 확인</Link><Link className="btn ghost" to={`/services/${service.id}`}>Back to builder</Link></div></header>
    <div className="run-input-layout">
      <form className="run-input-card" onSubmit={run}>
        <span className="eyebrow">EXECUTION INPUT</span>
        <h2>이번 실행의 입력 파일</h2>
        <p className="run-prefill-note">{prefillSource}으로 미리 채웠습니다. 바꿀 파일만 바꾸세요. 여기서 고른 파일은 이번 실행에만 쓰이고 워크플로우 기본값은 그대로입니다.{droppedFiles > 0 && ` 이전 실행 파일 중 삭제된 ${droppedFiles}개는 제외했습니다.`}</p>
        <div className="run-entries">
          {entries.map((entry) => {
            const current = selected(entry)
            const changed = !sameIds(current, entry.defaults)
            return <div className={`run-entry ${current.length || entry.directories.length ? '' : 'empty'}`} key={`${entry.kind}-${entry.id}`}>
              <div className="run-entry-head">
                <div><strong>{entry.label}</strong>{entry.format && <small>예상 형식: {entry.format}</small>}<small>{entry.kind === 'slot' ? `읽는 블록: ${entry.blocks.join(', ') || '없음'}` : '블록에 직접 연결된 파일'}</small></div>
                {changed && <span className="run-entry-changed">이번 실행에서 변경됨</span>}
              </div>
              <div className="slot-sources">
                {current.map((fileId) => <span className="source-chip upload" key={fileId}><span>{fileName(fileId)}</span><small>업로드 · 서버를 거쳐 전달</small><button type="button" aria-label="이번 실행에서 빼기" onClick={() => setSelected(entry, current.filter((value) => value !== fileId))}>×</button></span>)}
                {entry.directories.map((directoryId) => <span className="source-chip directory" key={`d${directoryId}`}><span>공유 디렉터리 #{directoryId}</span><small>해당 기기 안에서만 읽음</small></span>)}
                {!current.length && !entry.directories.length && <span className="muted">파일이 없습니다.</span>}
              </div>
              <div className="slot-actions">
                <button type="button" className="btn sm" disabled={loading} onClick={() => startUpload(entry)}>파일 올리기</button>
                <select value="" onChange={(event) => event.target.value && setSelected(entry, [...current, Number(event.target.value)])}>
                  <option value="">업로드한 파일에서 추가</option>
                  {files.filter((file) => !current.includes(file.id)).map((file) => <option key={file.id} value={file.id}>{file.original_name}</option>)}
                </select>
                {changed && <button type="button" className="text-button" onClick={() => setSelected(entry, entry.defaults)}>기본값으로</button>}
              </div>
            </div>
          })}
          {!entries.length && <p className="muted">이 워크플로우에는 파일 입력이 없습니다.</p>}
        </div>
        {blockEntries.length > 0 && <div className="run-block-inputs">
          <div className="run-block-inputs-head"><strong>블록 입력</strong><Link className="text-button" to={`/services/${service.id}`}>편집 화면에서 바꾸기</Link></div>
          {blockEntries.map(({ agent, isStart, inputs }) => <div className={`run-block-input${inputs.missing ? ' missing' : ''}`} key={agent.id}>
            <span>{agent.name}{isStart && <small>시작 블록</small>}</span>
            <strong>{inputs.label}</strong>
            {inputs.hasText && <p>{agent.text_input!.trim()}</p>}
          </div>)}
        </div>}
        {validation && validation.errors.length > 0 && <><ValidationPanel validation={validation} nodeNames={Object.fromEntries(service.graph.nodes.map((node) => [node.id, node.name]))} showStages={false} /><Link className="btn sm ghost" to={`/services/${service.id}/setup`}>설정 확인 화면에서 고치기</Link></>}
        <div className="run-card-footer"><span>Workflow: <strong>{service.name}</strong></span><button className="generate-button" disabled={loading}>{loading ? 'Checking...' : 'Run workflow'} <b>→</b></button></div>
        {error && <div className="error">{error}</div>}
      </form>
      <aside className="run-summary-panel">
        <span className="eyebrow">WORKFLOW SUMMARY</span><h2>{service.name}</h2><p>{service.description || 'No workflow description provided.'}</p>
        <div className="run-summary-stat"><strong>{service.graph.nodes?.length ?? 0}</strong><span>workflow blocks</span></div>
        <p className="run-generation">생성 모델: {generationLabel(service.generation_info)}</p>
        <button type="button" className="btn ghost run-duplicate" onClick={duplicate}>워크플로우 복제</button>
        <div className="run-files-note"><div><strong>Input file vault</strong><small>{files.length} uploaded file{files.length === 1 ? '' : 's'}</small></div><p>업로드 파일은 서버를 거쳐 전달되고, 공유 디렉터리 파일은 해당 기기 안에서만 읽힙니다. 외부 API 단계는 실행 전에 전송 내용을 확인합니다.</p><Link to="/files">Manage files →</Link></div>
      </aside>
    </div>
    <input ref={uploadRef} className="inline-file-input" type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.pptx" onChange={onUpload} />
    {preview && <div className="file-library-modal-backdrop" role="presentation">
      <section className="file-library-modal input-review-modal" role="dialog" aria-modal="true" aria-labelledby="input-review-title">
        <header><div><span className="eyebrow">INPUT CHECK</span><h2 id="input-review-title">이 실행에 쓰이는 입력</h2></div><button className="modal-close" aria-label="닫기" onClick={() => setPreview(null)}>×</button></header>
        <p>실행하면 아래 파일과 텍스트가 각 블록으로 전달됩니다. 업로드 파일은 서버를 거쳐 전달되고, 공유 디렉터리 파일은 해당 기기 안에서만 읽힙니다.</p>
        <div className="input-review-body">
          <div className="input-review-totals">
            <span><b>{preview.review.totals.files}</b>파일{preview.review.totals.files > 0 && ` · ${formatBytes(preview.review.totals.bytes)}`}</span>
            <span><b>{preview.review.totals.directories}</b>공유 디렉터리</span>
            <span><b>{preview.review.totals.texts}</b>텍스트 데이터</span>
          </div>
          {preview.review.blocks.map((block) => <div className="input-review-block" key={block.node_id}>
            <div className="input-review-block-head"><strong>{block.name}</strong><span className={`input-review-badge${block.is_start ? ' start' : ''}`}>{block.is_start ? '시작 블록' : '직접 입력'}</span><small>{destination(block)}</small></div>
            <ul>
              {block.files.map((file) => <li className="upload" key={`f${file.id}`}><span>{file.name}</span><small>{formatBytes(file.size_bytes)} · 서버 → {block.executor === 'cloud' ? providerName(block.provider) : block.device_name ?? '배정된 워커'}</small></li>)}
              {block.directories.map((directory) => <li className="directory" key={`d${directory.id}`}><span>디렉터리 · {directory.alias}</span><small>{directory.device_name ?? '해당 기기'} 안에서만 읽음</small></li>)}
              {block.text && <li className="text"><span>텍스트 데이터</span><p>{block.text}</p></li>}
              {block.allow_no_input && <li className="none"><span>입력 없이 실행</span><small>역할 프롬프트만으로 시작합니다.</small></li>}
            </ul>
          </div>)}
          {preview.requires_consent && <div className="input-review-section consent">
            <strong>외부 API 전송</strong>
            <small>API 키는 서버에만 보관되며 아래 입력과 결과만 외부 공급자에 전달됩니다.</small>
            <div className="transfer-list">{preview.transfers.map((item, index) => <div className={`transfer-item ${item.type}`} key={`${item.node_id}-${item.type}-${index}`}><strong>{item.node_name} → {providerName(item.provider)}</strong><span>{item.type === 'user_input' ? '블록 입력과 앞 단계 결과' : item.type === 'text_input' ? '블록 텍스트 데이터' : item.type === 'derived_text' ? `로컬 파일에서 파생된 텍스트: ${(item.sources || []).join(', ')}` : `첨부파일에서 추출한 텍스트: ${(item.file_ids || []).map(fileName).join(', ')}`}</span></div>)}</div>
          </div>}
          {preview.validation.warnings.length > 0 && <div className="input-review-section warnings">
            <strong>구성 경고</strong>
            <ul className="validation-list">{preview.validation.warnings.map((issue, index) => <li className="warning" key={`${issue.code}-${index}`}>{issue.message}</li>)}</ul>
            <label className="ack-row"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />경고 내용을 확인했고 그대로 실행합니다.</label>
          </div>}
        </div>
        <footer><span>이번 실행에만 적용됩니다.</span><div><button className="btn sm ghost" onClick={() => setPreview(null)}>돌아가서 고치기</button><button className="btn sm" disabled={loading || (preview.validation.warnings.length > 0 && !acknowledged)} onClick={() => start(preview.consent_token)}>{preview.requires_consent ? '동의하고 실행' : '확인하고 실행'}</button></div></footer>
      </section>
    </div>}
  </div>
}
