import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import ValidationPanel from '../components/ValidationPanel'
import { AgentNode, Execution, ExecutionListItem, RunInputRecord, Service, UploadedFile, ValidationResult, WorkflowNode } from '../types'
import { generationLabel, onServiceRenamed } from '../workflow'

type Transfer = { node_id: string; node_name: string; provider: string; type: 'user_input' | 'derived_text' | 'file_text'; file_ids?: number[]; sources?: string[] }
type Preview = { requires_consent: boolean; consent_token: string | null; transfers: Transfer[]; validation: ValidationResult }
type RunInputs = { slots: Record<string, number[]>; nodes: Record<string, number[]> }
type InputEntry = { kind: 'slot' | 'node'; id: string; label: string; format?: string; blocks: string[]; directories: number[]; defaults: number[]; split: boolean }

const isAgent = (node: WorkflowNode): node is AgentNode => !node.type || node.type === 'agent'
const sameIds = (a: number[], b: number[]) => a.length === b.length && a.every((value, index) => value === b[index])

/** 실행 화면: 주 입력은 이번 실행의 입력 파일이고, 실행 프롬프트는 선택 사항이다. */
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
  const [prompt, setPrompt] = useState('')
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
      split: agents.some((agent) => agent.split?.enabled && (agent.input_slot_ids ?? []).includes(slot.id)),
    }))
    // 슬롯 없이 블록에 직접 파일을 붙인 이전 버전 워크플로우
    const nodeEntries = agents
      .filter((agent) => (agent.uploaded_file_ids ?? []).length || (agent.needs_file && !(agent.input_slot_ids ?? []).length))
      .map((agent) => ({ kind: 'node' as const, id: agent.id, label: agent.name, blocks: [agent.name], directories: [], defaults: agent.uploaded_file_ids ?? [], split: !!agent.split?.enabled }))
    return [...slotEntries, ...nodeEntries]
  }, [service])

  useEffect(() => {
    async function load() {
      try {
        const [loaded, loadedFiles] = await Promise.all([api.get<Service>(`/services/${id}`), api.get<UploadedFile[]>('/files')])
        setService(loaded)
        setFiles(loadedFiles)
        // 지정한 실행(다시 실행) 또는 이 워크플로우의 가장 최근 실행 값으로 입력 파일을 미리 채운다
        let previous: { id: number; run_prompt: string; input_files?: RunInputRecord[] | null } | undefined
        if (fromExecution) previous = await api.get<Execution>(`/executions/${fromExecution}`).catch(() => undefined)
        else previous = (await api.get<ExecutionListItem[]>(`/executions?service_id=${id}`).catch(() => []))[0]
        const existing = new Set(loadedFiles.map((file) => file.id))
        const next: RunInputs = { slots: {}, nodes: {} }
        let dropped = 0
        for (const record of previous?.input_files ?? []) {
          // 나눠 실행한 기록은 원본 파일이 슬롯·블록 기록에 이미 들어 있다
          if (record.kind === 'split') continue
          const ids = record.files.map((file) => file.id)
          const kept = ids.filter((fileId) => existing.has(fileId))
          dropped += ids.length - kept.length
          if (record.kind === 'slot') next.slots[record.id] = kept
          else next.nodes[record.id] = kept
        }
        setInputs(next)
        setDroppedFiles(dropped)
        if (previous?.input_files?.length) setPrefillSource(`이전 실행 #${previous.id} 값`)
        // 다시 실행할 때는 그 실행의 프롬프트도 가져온다
        if (fromExecution && previous?.run_prompt) setPrompt(previous.run_prompt)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : '워크플로우를 불러오지 못했어요.')
      }
    }
    load()
  }, [id, fromExecution])

  useEffect(() => onServiceRenamed((renamed) => {
    if (String(renamed.id) === id) setService((current) => (current ? { ...current, name: renamed.name } : current))
  }), [id])

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
      const execution = await api.post<Execution>(`/services/${id}/executions`, { run_prompt: prompt, input_files: payloadInputs(), consent_token: consentToken || null, acknowledge_warnings: acknowledged })
      navigate(`/executions/${execution.id}`)
    } catch (cause) {
      setPreview(null)
      showValidationFrom(cause)
      setError(cause instanceof Error ? cause.message : '실행을 시작하지 못했어요.')
    } finally {
      setLoading(false)
    }
  }

  async function run(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const result = await api.post<Preview>(`/services/${id}/executions/preview`, { run_prompt: prompt, input_files: payloadInputs() })
      setValidation(result.validation)
      if (result.validation.errors.length) { setError('구성 오류를 고친 뒤 실행할 수 있습니다.'); return }
      if (result.validation.warnings.length && !acknowledged) { setError('구성 경고를 확인하고 체크한 뒤 다시 실행해 주세요.'); return }
      if (result.requires_consent) setPreview(result)
      else await start()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '워크플로우를 확인하지 못했어요.')
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

  if (!service) return <div className="page-loading">{error || '워크플로우를 불러오는 중…'}</div>
  const fileName = (fileId: number) => files.find((file) => file.id === fileId)?.original_name || `File #${fileId}`

  return <div className="workflow-run-page">
    <header className="page-topbar"><div><div className="breadcrumb">M.A.R.S <span>/</span> 워크플로우 <span>/</span> {service.name} <span>/</span> 실행</div><h1>실행 설정</h1><p>이번 실행에 쓸 입력 파일을 확인하고 실행해요.</p></div></header>
    <div className="run-input-layout">
      <form className="run-input-card" onSubmit={run}>
        <span className="eyebrow">실행 입력</span>
        <h2>이번 실행의 입력 파일</h2>
        <p className="run-prefill-note">{prefillSource}으로 미리 채웠어요. 여기서 바꾼 파일은 이번 실행에만 쓰여요.{droppedFiles > 0 && ` 이전 실행 파일 중 삭제된 ${droppedFiles}개는 뺐어요.`}</p>
        <div className="run-entries">
          {entries.map((entry) => {
            const current = selected(entry)
            const changed = !sameIds(current, entry.defaults)
            return <div className={`run-entry ${current.length || entry.directories.length ? '' : 'empty'}`} key={`${entry.kind}-${entry.id}`}>
              <div className="run-entry-head">
                <div><strong>{entry.label}</strong>{entry.format && <small>예상 형식: {entry.format}</small>}{entry.kind === 'slot' && <small>읽는 블록: {entry.blocks.join(', ') || '없음'}</small>}{entry.split && <small className="run-entry-split">나눠서 병렬 실행 · 실행할 때 온라인 워커 수에 맞춰 파일을 나눠요</small>}</div>
                {changed && <span className="run-entry-changed">이번 실행에서 변경됨</span>}
              </div>
              <div className="slot-sources">
                {current.map((fileId) => <span className="source-chip upload" key={fileId}><span>{fileName(fileId)}</span><small>업로드 · 서버를 거쳐 전달</small><button type="button" aria-label="이번 실행에서 빼기" onClick={() => setSelected(entry, current.filter((value) => value !== fileId))}>×</button></span>)}
                {entry.directories.map((directoryId) => <span className="source-chip directory" key={`d${directoryId}`}><span>등록한 폴더 #{directoryId}</span><small>그 PC에서만 읽음</small></span>)}
                {!current.length && !entry.directories.length && <span className="muted">파일 없음</span>}
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
          {!entries.length && <p className="muted">이 워크플로우는 입력 파일이 없어요. 필요한 지시는 실행 프롬프트에 적어 주세요.</p>}
        </div>
        <label className="run-prompt-label">실행 프롬프트 <small>(선택)</small></label>
        <textarea className="run-prompt-input" value={prompt} onChange={(event) => { setPrompt(event.target.value); setValidation(null) }} placeholder="이번 실행에만 덧붙일 지시가 있으면 적어 주세요. 비워 두면 입력 파일과 설정만으로 실행해요." />
        {validation && (validation.errors.length > 0 || validation.warnings.length > 0) && <><ValidationPanel validation={validation} nodeNames={Object.fromEntries(service.graph.nodes.map((node) => [node.id, node.name]))} showStages={false} />{validation.errors.length > 0 && <Link className="btn sm ghost" to={`/services/${service.id}/setup`}>설정 확인 화면에서 고치기</Link>}{!validation.errors.length && <label className="ack-row"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />경고 내용을 확인했고 그대로 실행합니다.</label>}</>}
        <div className="run-card-footer"><button className="generate-button" disabled={loading}>{loading ? '확인 중…' : '실행하기'} <b>→</b></button></div>
        {error && <div className="error">{error}</div>}
      </form>
      <aside className="run-summary-panel">
        <span className="eyebrow">워크플로우 요약</span><h2>{service.name}</h2>{service.description && service.description.trim() !== service.name.trim() && <p>{service.description}</p>}
        <p className="run-summary-meta">블록 {service.graph.nodes?.length ?? 0}개 · 생성 모델 {generationLabel(service.generation_info)}</p>
        <button type="button" className="btn ghost run-duplicate" onClick={duplicate}>워크플로우 복제</button>
        <div className="run-files-note"><div><strong>입력 파일 보관함</strong><small>{files.length}개</small></div><Link to="/files">파일 관리 →</Link></div>
      </aside>
    </div>
    <input ref={uploadRef} className="inline-file-input" type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.log,.jsonl,.xlsx,.pptx" onChange={onUpload} />
    {preview && <div className="file-library-modal-backdrop" role="presentation"><section className="file-library-modal transfer-consent-modal" role="dialog" aria-modal="true" aria-labelledby="transfer-title"><header><div><span className="eyebrow">외부 전송</span><h2 id="transfer-title">클라우드 전송 내용을 확인해 주세요</h2></div><button className="modal-close" onClick={() => setPreview(null)}>×</button></header><p>API 키는 서버에만 보관되며 아래 입력과 결과만 외부 공급자에 전달됩니다.</p><div className="transfer-list">{preview.transfers.map((item, index) => <div className={`transfer-item ${item.type}`} key={`${item.node_id}-${item.type}-${index}`}><strong>{item.node_name} → {item.provider}</strong><span>{item.type === 'user_input' ? '사용자 실행 요청' : item.type === 'derived_text' ? `로컬 파일에서 파생된 텍스트: ${(item.sources || []).join(', ')}` : `첨부파일에서 추출한 텍스트: ${(item.file_ids || []).map(fileName).join(', ')}`}</span></div>)}</div><footer><span>이번 실행에만 적용됩니다.</span><div><button className="btn sm ghost" onClick={() => setPreview(null)}>취소</button><button className="btn sm" disabled={loading} onClick={() => start(preview.consent_token)}>동의하고 실행</button></div></footer></section></div>}
  </div>
}
