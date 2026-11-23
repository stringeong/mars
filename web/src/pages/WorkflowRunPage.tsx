import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { fileLabel, fileMeta, newestFirst, useFilePreview } from '../components/FilePreview'
import ValidationPanel from '../components/ValidationPanel'
import { AgentNode, Execution, ExecutionListItem, RunInputRecord, Service, SplitPreview, UploadedFile, ValidationIssue, ValidationResult, WorkflowNode } from '../types'
import { firstInputSlot, generationLabel, onServiceRenamed, splitPreviewText } from '../workflow'

type Transfer = { node_id: string; node_name: string; provider: string; type: 'user_input' | 'derived_text' | 'file_text'; file_ids?: number[]; sources?: string[] }
type Preview = { requires_consent: boolean; consent_token: string | null; transfers: Transfer[]; validation: ValidationResult }
type RunInputs = { slots: Record<string, number[]>; nodes: Record<string, number[]>; split?: Record<string, boolean | { enabled: boolean; parts: 'auto' | number }> }
type InputEntry = { kind: 'slot' | 'node'; id: string; label: string; format?: string; blocks: string[]; blockIds: string[]; directories: number[]; defaults: number[]; split: boolean }

// 줄·행 단위로 나눌 수 있는 파일과, 실행 화면에서 '나눠서 병렬 실행'을 기본으로 켜는 크기(조각 최대 글자 수 기본값)
const SPLITTABLE = /\.(txt|log|md|jsonl|csv|json)$/i
const AUTO_SPLIT_BYTES = 12000
const entryKey = (entry: InputEntry) => `${entry.kind}:${entry.id}`

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
  // 파일 나눠서 병렬 실행: 지금 올린 파일과 사용 가능한 워커 수로 정한 분할 계획 (실행 전에 미리 보여준다)
  // cuts: 파일이 길어 뒷부분이 빠질 입력 (나누지 않고 실행할 때). 실행을 누르기 전에 파일 아래에 미리 알린다
  const [plan, setPlan] = useState<{ splits: SplitPreview[]; issues: string[]; cuts: ValidationIssue[]; loading: boolean }>({ splits: [], issues: [], cuts: [], loading: false })
  // 실행 화면에서 사용자가 직접 켜거나 끈 '나눠서 병렬 실행' (입력 칸별). 없으면 기본 규칙을 따른다
  const [splitChoice, setSplitChoice] = useState<Record<string, boolean>>({})
  // 조각 수: 고르지 않으면 편집 화면 설정(없으면 자동), 고르면 이번 실행에만 그 값
  const [splitParts, setSplitParts] = useState<Record<string, 'auto' | number>>({})
  const [acknowledged, setAcknowledged] = useState(false)
  const [uploadTarget, setUploadTarget] = useState<InputEntry | null>(null)
  const uploadRef = useRef<HTMLInputElement>(null)
  const filePreview = useFilePreview()

  const entries = useMemo<InputEntry[]>(() => {
    if (!service) return []
    const agents = service.graph.nodes.filter(isAgent)
    const slots = service.graph.input_slots ?? []
    // 슬롯이 있는 블록에 예전 방식으로 직접 붙은 파일은 따로 칸을 만들지 않고 그 블록의 첫 번째 슬롯 칸 기본값에 합친다
    const directFiles = (slotId: string) => agents.filter((agent) => firstInputSlot(agent, slots)?.id === slotId).flatMap((agent) => agent.uploaded_file_ids ?? [])
    const slotEntries = slots.map((slot) => ({
      kind: 'slot' as const,
      id: slot.id,
      label: slot.description || '사용자 파일',
      format: slot.format,
      blocks: agents.filter((agent) => (agent.input_slot_ids ?? []).includes(slot.id)).map((agent) => agent.name),
      blockIds: agents.filter((agent) => (agent.input_slot_ids ?? []).includes(slot.id)).map((agent) => agent.id),
      directories: slot.directory_ids,
      defaults: [...new Set([...slot.file_ids, ...directFiles(slot.id)])],
      split: agents.some((agent) => agent.split?.enabled && (agent.input_slot_ids ?? []).includes(slot.id)),
    }))
    // 슬롯 없이 블록에 직접 파일을 붙인 이전 버전 워크플로우
    const nodeEntries = agents
      .filter((agent) => !firstInputSlot(agent, slots) && ((agent.uploaded_file_ids ?? []).length || (agent.needs_file && !(agent.input_slot_ids ?? []).length)))
      .map((agent) => ({ kind: 'node' as const, id: agent.id, label: agent.name, blocks: [agent.name], blockIds: [agent.id], directories: [], defaults: agent.uploaded_file_ids ?? [], split: !!agent.split?.enabled }))
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
        else {
          const latest = (await api.get<ExecutionListItem[]>(`/executions?service_id=${id}`).catch(() => []))[0]
          // 마지막 실행 뒤에 워크플로우를 고쳤으면(블록 파일 교체 등) 이전 실행 값 대신 지금 블록·슬롯 파일을 쓴다
          if (latest && Date.parse(loaded.updated_at) > Date.parse(latest.created_at)) setPrefillSource(`워크플로우 기본값(이전 실행 #${latest.id} 뒤에 수정됨)`)
          else previous = latest
        }
        const existing = new Set(loadedFiles.map((file) => file.id))
        const loadedAgents = loaded.graph.nodes.filter(isAgent)
        const next: RunInputs = { slots: {}, nodes: {} }
        const addSlot = (slotId: string, fileIds: number[]) => { next.slots[slotId] = [...new Set([...(next.slots[slotId] ?? []), ...fileIds])] }
        let dropped = 0
        for (const record of previous?.input_files ?? []) {
          // 나눠 실행한 기록은 원본 파일이 슬롯·블록 기록에 이미 들어 있다
          if (record.kind === 'split') continue
          const ids = record.files.map((file) => file.id)
          const kept = ids.filter((fileId) => existing.has(fileId))
          dropped += ids.length - kept.length
          // 슬롯이 있는 블록의 직접 파일 기록(예전 실행)은 그 블록의 첫 번째 슬롯 칸에 합친다
          const slotOfNode = record.kind === 'node' ? firstInputSlot(loadedAgents.find((agent) => agent.id === record.id), loaded.graph.input_slots ?? []) : undefined
          if (record.kind === 'slot') addSlot(record.id, kept)
          else if (slotOfNode) addSlot(slotOfNode.id, kept)
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

  // 입력 파일이 바뀔 때마다 서버에 "이 파일이면 몇 조각이 되는지"를 물어본다. 워커 상태도 그때그때 반영한다.
  // 이번 실행에서 나눠서 실행할 블록 (실행 화면 스위치 기준)
  const splitIdSet = new Set(entries.filter(splitOn).flatMap((entry) => entry.blockIds))
  const splitBlocks = (service?.graph.nodes ?? []).filter(isAgent).filter((agent) => splitIdSet.has(agent.id))
  const inputsKey = JSON.stringify(inputs) + JSON.stringify([...splitIdSet].sort()) + JSON.stringify(splitParts)
  const hasFiles = entries.some((entry) => selected(entry).length > 0)
  useEffect(() => {
    if (!service || (!splitBlocks.length && !hasFiles)) { setPlan({ splits: [], issues: [], cuts: [], loading: false }); return }
    let cancelled = false
    setPlan((current) => ({ ...current, loading: true }))
    const timer = window.setTimeout(async () => {
      try {
        const result = await api.post<Preview>(`/services/${id}/executions/preview`, { run_prompt: prompt, input_files: payloadInputs() })
        if (cancelled) return
        const splitIds = new Set(splitBlocks.map((block) => block.id))
        const issues = [...result.validation.errors, ...result.validation.warnings]
          .filter((issue) => issue.code.startsWith('split_') || (issue.code === 'missing_file' && issue.node_ids.some((nodeId) => splitIds.has(nodeId))))
          .map((issue) => issue.message)
        const cuts = result.validation.warnings.filter((issue) => issue.code === 'input_cut')
        setPlan({ splits: result.validation.splits ?? [], issues, cuts, loading: false })
      } catch {
        if (!cancelled) setPlan({ splits: [], issues: [], cuts: [], loading: false })
      }
    }, 350)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [service, inputsKey, files, id])

  useEffect(() => onServiceRenamed((renamed) => {
    if (String(renamed.id) === id) setService((current) => (current ? { ...current, name: renamed.name } : current))
  }), [id])

  function selected(entry: InputEntry) {
    const bucket = entry.kind === 'slot' ? inputs.slots : inputs.nodes
    return bucket[entry.id] ?? entry.defaults
  }

  /** 나눌 수 있는 텍스트 파일(.txt .log .md .jsonl .csv)이 들어 있는지 */
  function splittableFiles(entry: InputEntry) {
    return selected(entry).map((fileId) => files.find((file) => file.id === fileId)).filter((file): file is UploadedFile => !!file && SPLITTABLE.test(file.original_name))
  }
  /** 이 입력 칸에 '나눠서 병렬 실행' 스위치를 보여줄지: 나눌 수 있는 파일이 있거나 편집 화면에서 켜 둔 경우 */
  function splitOffered(entry: InputEntry) {
    return entry.blockIds.length > 0 && (entry.split || splittableFiles(entry).length > 0)
  }
  /** 직접 고른 값이 없으면, 편집 화면에서 켜 뒀거나 텍스트 파일이 충분히 크면 켠다 */
  function splitDefault(entry: InputEntry) {
    return entry.split || splittableFiles(entry).reduce((sum, file) => sum + file.size_bytes, 0) >= AUTO_SPLIT_BYTES
  }
  function splitOn(entry: InputEntry) {
    return splitOffered(entry) && (splitChoice[entryKey(entry)] ?? splitDefault(entry))
  }
  function chooseParts(entry: InputEntry, parts: 'auto' | number) {
    setSplitParts((current) => ({ ...current, [entryKey(entry)]: parts }))
    setValidation(null)
    setAcknowledged(false)
  }
  function chooseSplit(entry: InputEntry, on: boolean) {
    setSplitChoice((current) => ({ ...current, [entryKey(entry)]: on }))
    setValidation(null)
    setAcknowledged(false)
  }

  function setSelected(entry: InputEntry, fileIds: number[]) {
    const key = entry.kind === 'slot' ? 'slots' : 'nodes'
    setInputs((current) => ({ ...current, [key]: { ...current[key], [entry.id]: [...new Set(fileIds)] } }))
    // 파일이 바뀌면 직접 고른 분할 여부를 지우고 새 파일 크기로 다시 정한다
    setSplitChoice((current) => { const next = { ...current }; delete next[entryKey(entry)]; return next })
    setValidation(null)
    setAcknowledged(false)
  }

  // 화면의 모든 입력 칸을 보낸다. 미리보기와 실행에 같은 값을 보내야 외부 전송 동의가 맞물린다.
  function payloadInputs(): RunInputs {
    const payload: RunInputs = { slots: {}, nodes: {}, split: {} }
    entries.forEach((entry) => {
      payload[entry.kind === 'slot' ? 'slots' : 'nodes'][entry.id] = selected(entry)
      // 스위치가 보이는 입력 칸만 보낸다. 나머지 블록은 저장된 설정을 그대로 쓴다
      if (splitOffered(entry)) {
        const parts = splitParts[entryKey(entry)]
        entry.blockIds.forEach((blockId) => { payload.split![blockId] = parts === undefined || !splitOn(entry) ? splitOn(entry) : { enabled: true, parts } })
      }
    })
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
                <div><strong>{entry.label}</strong>{entry.format && <small>예상 형식: {entry.format}</small>}{entry.kind === 'slot' && <small>읽는 블록: {entry.blocks.join(', ') || '없음'}</small>}</div>
                {changed && <span className="run-entry-changed">이번 실행에서 변경됨</span>}
              </div>
              {splitOffered(entry) && <label className={`run-split-toggle${splitOn(entry) ? ' on' : ''}`}>
                <input type="checkbox" checked={splitOn(entry)} onChange={(event) => chooseSplit(entry, event.target.checked)} />
                <span><b>파일 나눠서 병렬 실행</b><small>{splitChoice[entryKey(entry)] !== undefined ? '이번 실행에서 직접 정했어요.' : entry.split ? '편집 화면에서 켜 둔 설정이에요.' : splitDefault(entry) ? `큰 텍스트 파일이라 자동으로 켰어요. 워커 수에 맞춰 나눠서 동시에 처리해요.` : '파일이 작아 꺼 뒀어요. 켜면 워커 수만큼 나눠요.'} 전체 맥락이 필요한 자료는 끄세요.</small></span>
              </label>}
              {splitOn(entry) && <div className="run-split-parts" role="group" aria-label="조각 수">
                <span>조각 수</span>
                <button type="button" className={(splitParts[entryKey(entry)] ?? 'auto') === 'auto' ? 'active' : ''} onClick={() => chooseParts(entry, 'auto')}>자동 (워커 수에 맞춤)</button>
                <button type="button" className={typeof splitParts[entryKey(entry)] === 'number' ? 'active' : ''} onClick={() => chooseParts(entry, typeof splitParts[entryKey(entry)] === 'number' ? splitParts[entryKey(entry)] : Math.max(2, plan.splits.find((item) => entry.blockIds.includes(item.node_id))?.parts ?? 2))}>직접 정하기</button>
                {typeof splitParts[entryKey(entry)] === 'number' && <label className="run-split-count"><input type="number" min={2} max={50} value={splitParts[entryKey(entry)] as number} onChange={(event) => chooseParts(entry, Math.min(50, Math.max(2, Math.round(Number(event.target.value)) || 2)))} aria-label="조각 수 직접 입력" />개</label>}
                <small>{typeof splitParts[entryKey(entry)] === 'number' ? '워커가 적으면 한 워커가 여러 조각을 차례로 처리해요.' : '사용 가능한 워커 수와 파일 크기로 정해요.'}</small>
              </div>}
              <div className="slot-sources">
                {current.map((fileId) => { const file = files.find((item) => item.id === fileId); return <span className="source-chip upload" key={fileId}>{file ? <button type="button" className="file-open" title="미리보기" onClick={() => filePreview.open(file)}>{file.original_name}</button> : <span>{fileName(fileId)}</span>}<small>{file && `${fileMeta(file)} · `}업로드 · 서버를 거쳐 전달</small><button type="button" aria-label="이번 실행에서 빼기" onClick={() => setSelected(entry, current.filter((value) => value !== fileId))}>×</button></span> })}
                {entry.directories.map((directoryId) => <span className="source-chip directory" key={`d${directoryId}`}><span>등록한 폴더 #{directoryId}</span><small>그 PC에서만 읽음</small></span>)}
                {!current.length && !entry.directories.length && <span className="muted">파일 없음</span>}
              </div>
              {plan.cuts.filter((issue) => issue.node_ids.some((nodeId) => entry.blockIds.includes(nodeId))).map((issue) => <p className="run-entry-cut" role="status" key={issue.message}>{issue.message.replace(/^'[^']*'\s*블록의\s*/, '')}</p>)}
              <div className="slot-actions">
                <button type="button" className="btn sm" disabled={loading} onClick={() => startUpload(entry)}>파일 올리기</button>
                <select value="" onChange={(event) => event.target.value && setSelected(entry, [...current, Number(event.target.value)])}>
                  <option value="">업로드한 파일에서 추가</option>
                  {newestFirst(files).filter((file) => !current.includes(file.id)).map((file) => <option key={file.id} value={file.id}>{fileLabel(file)}</option>)}
                </select>
                {changed && <button type="button" className="text-button" onClick={() => setSelected(entry, entry.defaults)}>기본값으로</button>}
              </div>
            </div>
          })}
          {!entries.length && <p className="muted">이 워크플로우는 입력 파일이 없어요. 필요한 지시는 실행 프롬프트에 적어 주세요.</p>}
        </div>
        {splitBlocks.length > 0 && <section className="split-plan" aria-live="polite">
          <div className="split-plan-head"><strong>파일 나눠서 병렬 실행</strong><small>{plan.loading ? '계획을 계산하는 중…' : '실행하면 이렇게 나뉘어요'}</small></div>
          {splitBlocks.map((block) => {
            const preview = plan.splits.find((item) => item.node_id === block.id)
            const total = preview ? preview.sizes.reduce((sum, size) => sum + size, 0) : 0
            return <div className="split-plan-block" key={block.id}>
              <div className="split-plan-title"><b>{block.name}</b>{preview?.source_name && <span>{preview.source_name}</span>}</div>
              {preview ? <>
                <p className="split-plan-summary">{splitPreviewText(preview)}</p>
                <div className="split-plan-flow" aria-hidden="true">
                  <div className="split-plan-file"><b>{preview.source_name ?? '입력 파일'}</b><small>{preview.unit === 'file' ? `파일 ${total}개` : `${total.toLocaleString()}${preview.unit_label}`}</small></div>
                  <i>→ {preview.workers}대 워커가 나눠 처리 →</i>
                  <div className="split-plan-pieces">{preview.sizes.map((size, index) => <div key={index} className="split-plan-piece" style={{ flexGrow: Math.max(1, size) }}><b>{block.name} #{index + 1}</b><small>{size.toLocaleString()}{preview.unit_label}</small></div>)}</div>
                </div>
                <small className="split-plan-note">조각마다 같은 블록으로 펼쳐져 비어 있는 워커가 하나씩 가져가요. 다음 블록은 조각 결과를 원본 순서대로 받아요.{preview.overlap_lines > 0 && ` 각 조각 앞에는 직전 ${preview.overlap_lines}줄이 참고용으로 붙어요.`} 나누는 방식은 <Link to={`/services/${service.id}`}>편집 화면</Link>에서 바꿀 수 있어요.</small>
              </> : plan.issues.length ? <ul className="split-plan-issues">{plan.issues.map((message) => <li key={message}>{message}</li>)}</ul>
                : <p className="split-plan-summary muted">{plan.loading ? '계산하는 중…' : '파일을 올리면 몇 조각으로 나뉘는지 여기에 보여줘요.'}</p>}
            </div>
          })}
        </section>}
        <label className="run-prompt-label">실행 프롬프트 <small>(선택)</small></label>
        <textarea className="run-prompt-input" value={prompt} onChange={(event) => { setPrompt(event.target.value); setValidation(null) }} placeholder="이번 실행에만 덧붙일 지시가 있으면 적어 주세요. 비워 두면 입력 파일과 설정만으로 실행해요." />
        {validation && (validation.errors.length > 0 || validation.warnings.length > 0) && <><ValidationPanel validation={validation} nodeNames={Object.fromEntries(service.graph.nodes.map((node) => [node.id, node.name]))} showStages={false} />{validation.errors.length > 0 && <Link className="btn sm ghost" to={`/services/${service.id}/setup`}>설정 확인 화면에서 고치기</Link>}{!validation.errors.length && <label className="ack-row"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />경고 내용을 확인했고 그대로 실행합니다.</label>}</>}
        <div className="run-card-footer"><button className="generate-button" disabled={loading}>{loading ? '확인 중…' : '실행하기'} <b>→</b></button></div>
        {error && <div className="error">{error}</div>}
        {filePreview.error && <div className="error">{filePreview.error}</div>}
      </form>
      <aside className="run-summary-panel">
        <span className="eyebrow">워크플로우 요약</span><h2>{service.name}</h2>{service.description && service.description.trim() !== service.name.trim() && <p>{service.description}</p>}
        <p className="run-summary-meta">블록 {service.graph.nodes?.length ?? 0}개 · 생성 모델 {generationLabel(service.generation_info)}</p>
        <button type="button" className="btn ghost run-duplicate" onClick={duplicate}>워크플로우 복제</button>
        <div className="run-files-note"><div><strong>입력 파일 보관함</strong><small>{files.length}개</small></div><Link to="/files">파일 관리 →</Link></div>
      </aside>
    </div>
    <input ref={uploadRef} className="inline-file-input" type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.log,.jsonl,.xlsx,.pptx,.json" onChange={onUpload} />
    {filePreview.modal}
    {preview && <div className="file-library-modal-backdrop" role="presentation"><section className="file-library-modal transfer-consent-modal" role="dialog" aria-modal="true" aria-labelledby="transfer-title"><header><div><span className="eyebrow">외부 전송</span><h2 id="transfer-title">클라우드 전송 내용을 확인해 주세요</h2></div><button className="modal-close" onClick={() => setPreview(null)}>×</button></header><p>API 키는 서버에만 보관되며 아래 입력과 결과만 외부 공급자에 전달됩니다.</p><div className="transfer-list">{preview.transfers.map((item, index) => <div className={`transfer-item ${item.type}`} key={`${item.node_id}-${item.type}-${index}`}><strong>{item.node_name} → {item.provider}</strong><span>{item.type === 'user_input' ? '사용자 실행 요청' : item.type === 'derived_text' ? `로컬 파일에서 파생된 텍스트: ${(item.sources || []).join(', ')}` : `첨부파일에서 추출한 텍스트: ${(item.file_ids || []).map(fileName).join(', ')}`}</span></div>)}</div><footer><span>이번 실행에만 적용됩니다.</span><div><button className="btn sm ghost" onClick={() => setPreview(null)}>취소</button><button className="btn sm" disabled={loading} onClick={() => start(preview.consent_token)}>동의하고 실행</button></div></footer></section></div>}
  </div>
}
