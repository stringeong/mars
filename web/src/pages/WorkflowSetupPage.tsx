import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, getDeviceDirectories, getDeviceModels } from '../api'
import ValidationPanel from '../components/ValidationPanel'
import { AgentNode, CloudProvider, Device, DeviceModels, Graph, InputSlot, Service, SharedDirectory, UploadedFile, ValidationResult, WorkflowNode } from '../types'
import { applyAutoFlags, blockInputs, generationLabel, issuesByNode, onServiceRenamed, PROVIDER_LABELS } from '../workflow'

type Provider = NonNullable<AgentNode['provider']>
type ProviderStatus = { provider: CloudProvider; configured: boolean; default_model: string }
type SourceKey = 'file_ids' | 'directory_ids'

const CLOUD_PROVIDERS: CloudProvider[] = ['openai', 'anthropic', 'gemini']
const isAgent = (node: WorkflowNode): node is AgentNode => !node.type || node.type === 'agent'

/** 생성 직후 블록별 워커·모델·실행 위치와 입력 파일 슬롯을 한 표에서 확인하고 고치는 화면 */
export default function WorkflowSetupPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [service, setService] = useState<Service | null>(null)
  const [graph, setGraph] = useState<Graph | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [deviceModels, setDeviceModels] = useState<Record<number, DeviceModels>>({})
  const [deviceDirectories, setDeviceDirectories] = useState<Record<number, SharedDirectory[]>>({})
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [providers, setProviders] = useState<ProviderStatus[]>([])
  const [cloudModels, setCloudModels] = useState<Record<string, string[]>>({})
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [uploadTarget, setUploadTarget] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const uploadRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    async function load() {
      try {
        const [loaded, loadedDevices, loadedFiles, loadedProviders, models] = await Promise.all([
          api.get<Service>(`/services/${id}`),
          api.get<Device[]>('/devices'),
          api.get<UploadedFile[]>('/files'),
          api.get<ProviderStatus[]>('/settings/llm-providers'),
          api.get<Record<string, string[]>>('/settings/llm-models'),
        ])
        const [directoryGroups, modelGroups] = await Promise.all([
          Promise.all(loadedDevices.map((device) => getDeviceDirectories(device.id))),
          Promise.all(loadedDevices.map((device) => getDeviceModels(device.id))),
        ])
        setService(loaded)
        // 이전 버전에서 type 없이 저장된 블록도 에이전트로 다룬다
        setGraph({
          ...loaded.graph,
          nodes: loaded.graph.nodes.map((node) => (isAgent(node) ? { ...node, type: 'agent' } : node)),
          input_slots: loaded.graph.input_slots ?? [],
        })
        setDevices(loadedDevices)
        setDeviceDirectories(Object.fromEntries(loadedDevices.map((device, index) => [device.id, directoryGroups[index]])))
        setDeviceModels(Object.fromEntries(modelGroups.map((item) => [item.device_id, item])))
        setFiles(loadedFiles)
        setProviders(loadedProviders)
        setCloudModels(models)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : '불러오기 실패')
      }
    }
    load()
  }, [id])

  useEffect(() => onServiceRenamed((renamed) => {
    if (String(renamed.id) === id) setService((current) => (current ? { ...current, name: renamed.name } : current))
  }), [id])

  useEffect(() => {
    if (!graph) return
    const timer = window.setTimeout(() => {
      api.post<ValidationResult>(`/services/${id}/validate`, { graph }).then(setValidation).catch(() => {})
    }, 300)
    return () => window.clearTimeout(timer)
  }, [graph, id])

  const agents = useMemo(() => (graph?.nodes ?? []).filter(isAgent), [graph])
  const slots = graph?.input_slots ?? []
  const directories = useMemo(() => {
    const byId = new Map<number, SharedDirectory>()
    Object.values(deviceDirectories).flat().forEach((directory) => byId.set(directory.id, directory))
    return [...byId.values()]
  }, [deviceDirectories])
  const fileById = useMemo(() => new Map(files.map((file) => [file.id, file])), [files])
  const directoryById = useMemo(() => new Map(directories.map((directory) => [directory.id, directory])), [directories])
  const deviceById = useMemo(() => new Map(devices.map((device) => [device.id, device])), [devices])
  const issueMap = useMemo(() => issuesByNode(validation), [validation])
  const stageOf = useMemo(() => new Map((validation?.stages ?? []).flatMap((ids, index) => ids.map((nodeId) => [nodeId, index] as const))), [validation])
  const hasParent = useMemo(() => new Set((graph?.edges ?? []).filter((edge) => (edge.relation ?? 'workflow') === 'workflow').map((edge) => edge.target)), [graph])
  const nodeNames = useMemo(() => Object.fromEntries(agents.map((agent) => [agent.id, agent.name])), [agents])
  const flagReasons = useMemo(() => applyAutoFlags(agents, (graph?.edges ?? []).filter((edge) => (edge.relation ?? 'workflow') === 'workflow')).reasons, [agents, graph])

  function patchGraph(update: (current: Graph) => Graph) {
    setGraph((current) => (current ? update(current) : current))
    setDirty(true)
  }

  function updateNode(nodeId: string, patch: Partial<AgentNode>) {
    patchGraph((current) => ({ ...current, nodes: current.nodes.map((node) => (node.id === nodeId && isAgent(node) ? { ...node, ...patch } : node)) }))
  }

  function updateSlotSources(slotId: string, key: SourceKey, update: (values: number[]) => number[]) {
    patchGraph((current) => ({
      ...current,
      input_slots: (current.input_slots ?? []).map((slot) => (slot.id === slotId ? { ...slot, [key]: [...new Set(update(slot[key]))] } : slot)),
    }))
  }

  function createSlotFor(node: AgentNode) {
    patchGraph((current) => {
      const used = new Set((current.input_slots ?? []).map((slot) => slot.id))
      let index = used.size + 1
      while (used.has(`slot${index}`)) index += 1
      const slot: InputSlot = { id: `slot${index}`, description: `${node.name} 입력 파일`, format: '', file_ids: [], directory_ids: [] }
      return {
        ...current,
        input_slots: [...(current.input_slots ?? []), slot],
        // 자동으로 파일이 필요하지 않던 블록에 슬롯을 만들면 사용자가 직접 지정한 것으로 남긴다
        nodes: current.nodes.map((item) => (item.id === node.id && isAgent(item)
          ? { ...item, needs_file: true, needs_file_manual: item.needs_file ? item.needs_file_manual : true, input_slot_ids: [...(item.input_slot_ids ?? []), slot.id] }
          : item)),
      }
    })
  }

  function slotsOf(node: AgentNode) {
    return slots.filter((slot) => (node.input_slot_ids ?? []).includes(slot.id))
  }

  // 공유 디렉터리는 해당 기기 안에서만 읽히므로, 그 디렉터리가 있는 워커를 제안한다
  function suggestedWorker(node: AgentNode) {
    if ((node.provider || 'ollama') !== 'ollama') return undefined
    const directoryIds = [...new Set([...(node.directory_ids ?? []), ...slotsOf(node).flatMap((slot) => slot.directory_ids)])]
    if (!directoryIds.length) return undefined
    const candidates = devices.filter((device) => directoryIds.every((directoryId) => (deviceDirectories[device.id] ?? []).some((directory) => directory.id === directoryId)))
    return candidates.find((device) => device.online) ?? candidates[0]
  }

  function modelOptions(node: AgentNode) {
    const provider = node.provider || 'ollama'
    if (provider !== 'ollama') return cloudModels[provider] ?? []
    const relevant = node.worker_id ? devices.filter((device) => device.id === node.worker_id) : devices.filter((device) => device.online)
    return [...new Set(relevant.flatMap((device) => deviceModels[device.id]?.models ?? []))].sort()
  }

  function startUpload(slotId: string) {
    setUploadTarget(slotId)
    uploadRef.current?.click()
  }

  async function onUpload(event: ChangeEvent<HTMLInputElement>) {
    const slotId = uploadTarget
    const picked = event.target.files
    if (!slotId || !picked?.length) return
    setBusy(true)
    setError('')
    try {
      const uploaded: UploadedFile[] = []
      for (const file of Array.from(picked)) {
        const form = new FormData()
        form.append('file', file)
        uploaded.push(await api.upload<UploadedFile>('/files', form))
      }
      setFiles((current) => [...uploaded, ...current])
      updateSlotSources(slotId, 'file_ids', (values) => [...values, ...uploaded.map((file) => file.id)])
      const users = agents.filter((agent) => (agent.input_slot_ids ?? []).includes(slotId)).length
      setMessage(`${uploaded.length}개 파일을 올려 이 슬롯을 함께 읽는 블록 ${users}개에 연결했습니다. 저장해 주세요.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '파일 업로드 실패')
    } finally {
      setBusy(false)
      setUploadTarget(null)
      event.target.value = ''
    }
  }

  async function save(): Promise<Service | null> {
    if (!graph) return null
    setBusy(true)
    setError('')
    try {
      const updated = await api.put<Service>(`/services/${id}`, { graph })
      setService(updated)
      setValidation(updated.validation ?? null)
      setDirty(false)
      setMessage('저장되었습니다.')
      return updated
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '저장 실패')
      return null
    } finally {
      setBusy(false)
    }
  }

  async function saveAndRun() {
    const updated = dirty ? await save() : service
    if (!updated) return
    const blocking = (dirty ? updated.validation : validation)?.errors ?? []
    if (blocking.length) {
      setError(`실행하기 전에 오류 ${blocking.length}개를 고쳐 주세요: ${blocking[0].message}`)
      return
    }
    navigate(`/services/${id}/run`)
  }

  if (!service || !graph) return <div className="page-loading">{error || 'Loading workflow...'}</div>

  return <div className="setup-page">
    <header className="page-topbar">
      <div>
        <div className="breadcrumb">M.A.R.S <span>/</span> Workflows <span>/</span> {service.name} <span>/</span> Setup</div>
        <h1>설정 확인</h1>
        <p>생성된 블록의 실행 위치·워커·모델과 입력 파일을 한 곳에서 확인하고 고칩니다.</p>
        <div className="generation-badge"><span>생성 모델</span><strong>{generationLabel(service.generation_info)}</strong></div>
        {service.generation_info?.fallback_reason && <small className="generation-reason">기본 워크플로우를 고른 이유: {service.generation_info.fallback_reason}</small>}
      </div>
      <div className="builder-header-actions">
        <Link className="btn ghost" to={`/services/${id}`}>편집 화면</Link>
        <button className="btn ghost" disabled={busy || !dirty} onClick={save}>저장</button>
        <button className="btn" disabled={busy} onClick={saveAndRun}>{dirty ? '저장하고 실행 화면으로' : '실행 화면으로'}</button>
      </div>
    </header>
    {message && <div className="setup-message">{message}</div>}
    {error && <div className="error">{error}</div>}

    <div className="setup-layout">
      <div className="setup-main">
        <section className="setup-card">
          <div className="section-heading"><div><span className="eyebrow">INPUT FILES</span><h2>입력 파일 슬롯</h2></div><span className="count-pill">{slots.length}</span></div>
          <div className="file-route-notice">
            <strong>파일 전달 방식</strong>
            <p>업로드 파일은 서버를 거쳐 워커에 전달되고, 공유 디렉터리 파일은 해당 기기 안에서만 읽힙니다.</p>
          </div>
          {slots.map((slot) => {
            const users = agents.filter((agent) => (agent.input_slot_ids ?? []).includes(slot.id))
            const filled = slot.file_ids.length + slot.directory_ids.length > 0
            return <div className={`slot-card ${filled ? 'ready' : 'empty'}`} key={slot.id}>
              <div className="slot-card-head">
                <div><strong>{slot.description || '사용자 파일'}</strong>{slot.format && <p className="slot-format">예상 형식: {slot.format}</p>}</div>
                <span className={`slot-state ${filled ? 'ready' : 'empty'}`}>{filled ? '연결됨' : '비어 있음'}</span>
              </div>
              <div className="slot-users"><span>함께 읽는 블록</span>{users.map((user) => <b key={user.id}>{user.name}</b>)}{!users.length && <small className="muted">없음</small>}</div>
              <div className="slot-sources">
                {slot.file_ids.map((fileId) => <span className="source-chip upload" key={`f${fileId}`}>
                  <span>업로드 · {fileById.get(fileId)?.original_name ?? `파일 #${fileId}`}</span>
                  <small>서버를 거쳐 전달</small>
                  <button type="button" aria-label="연결 해제" onClick={() => updateSlotSources(slot.id, 'file_ids', (values) => values.filter((value) => value !== fileId))}>×</button>
                </span>)}
                {slot.directory_ids.map((directoryId) => {
                  const directory = directoryById.get(directoryId)
                  return <span className="source-chip directory" key={`d${directoryId}`}>
                    <span>디렉터리 · {directory?.alias ?? `#${directoryId}`}</span>
                    <small>{directory ? `${deviceById.get(directory.device_id)?.name ?? '기기'} 안에서만 읽음` : '삭제된 디렉터리'}</small>
                    <button type="button" aria-label="연결 해제" onClick={() => updateSlotSources(slot.id, 'directory_ids', (values) => values.filter((value) => value !== directoryId))}>×</button>
                  </span>
                })}
              </div>
              <div className="slot-actions">
                <button type="button" className="btn sm" disabled={busy} onClick={() => startUpload(slot.id)}>{busy && uploadTarget === slot.id ? '올리는 중…' : '파일 올리기'}</button>
                <select value="" onChange={(event) => event.target.value && updateSlotSources(slot.id, 'file_ids', (values) => [...values, Number(event.target.value)])}>
                  <option value="">기존 업로드 파일 연결</option>
                  {files.filter((file) => !slot.file_ids.includes(file.id)).map((file) => <option key={file.id} value={file.id}>{file.original_name}</option>)}
                </select>
                <select value="" onChange={(event) => event.target.value && updateSlotSources(slot.id, 'directory_ids', (values) => [...values, Number(event.target.value)])}>
                  <option value="">공유 디렉터리 연결</option>
                  {directories.filter((directory) => !slot.directory_ids.includes(directory.id)).map((directory) => <option key={directory.id} value={directory.id}>{directory.alias} · {deviceById.get(directory.device_id)?.name ?? '기기'}</option>)}
                </select>
              </div>
            </div>
          })}
          {!slots.length && <p className="muted">파일이 필요한 블록이 없습니다. 블록 표에서 파일 슬롯을 추가할 수 있습니다.</p>}
        </section>

        <section className="setup-card">
          <div className="section-heading"><div><span className="eyebrow">BLOCK SETTINGS</span><h2>블록별 설정</h2></div><span className="count-pill">{agents.length}</span></div>
          <div className="setup-table-wrap">
            <table className="setup-table">
              <thead><tr><th>블록</th><th>실행 위치</th><th>워커</th><th>모델</th><th>입력</th><th>검사</th></tr></thead>
              <tbody>
                {agents.map((node) => {
                  const provider: Provider = node.provider || 'ollama'
                  const isCloud = provider !== 'ollama'
                  const nodeSlots = slotsOf(node)
                  const suggestion = suggestedWorker(node)
                  const issues = issueMap.get(node.id) ?? []
                  const options = modelOptions(node)
                  const stage = stageOf.get(node.id)
                  const isStart = !hasParent.has(node.id)
                  const inputs = blockInputs(node, slots, isStart)
                  return <tr id={`setup-row-${node.id}`} key={node.id} className={issues.some((issue) => issue.severity === 'error') ? 'has-error' : issues.length ? 'has-warning' : ''}>
                    <td className="setup-block-cell">
                      <strong>{node.name}</strong>
                      <span>{stage !== undefined ? `${stage + 1}단계` : '단계 없음'}{node.final && <b className="mini-final">FINAL</b>}</span>
                      {node.needs_file && <small className="flag-reason" title={flagReasons[node.id]?.needsFile.reason}>파일 필요 · {flagReasons[node.id]?.needsFile.manual ? '직접 지정' : '자동'}</small>}
                    </td>
                    <td>
                      <select value={provider} onChange={(event) => {
                        const next = event.target.value as Provider
                        updateNode(node.id, { provider: next, executor: next === 'ollama' ? 'local' : 'cloud', worker_id: next === 'ollama' ? node.worker_id : null, model: '' })
                      }}>
                        <option value="ollama">로컬 워커 · Ollama</option>
                        {CLOUD_PROVIDERS.map((item) => {
                          const configured = providers.find((status) => status.provider === item)?.configured
                          return <option key={item} value={item} disabled={!configured && provider !== item}>외부 API · {PROVIDER_LABELS[item]}{configured ? '' : ' (키 없음)'}</option>
                        })}
                      </select>
                    </td>
                    <td>
                      <select disabled={isCloud} value={node.worker_id ?? ''} onChange={(event) => updateNode(node.id, { worker_id: event.target.value ? Number(event.target.value) : null, model: '' })}>
                        <option value="">자동 배정</option>
                        {devices.map((device) => <option key={device.id} value={device.id}>{device.name}{device.online ? '' : ' (오프라인)'}</option>)}
                      </select>
                      {isCloud && <small className="cell-hint">서버가 외부 API를 직접 호출</small>}
                      {suggestion && suggestion.id !== node.worker_id && <button type="button" className="suggest-chip" onClick={() => updateNode(node.id, { worker_id: suggestion.id, model: '' })}>추천: {suggestion.name} (디렉터리 위치) 적용</button>}
                    </td>
                    <td>
                      <select value={node.model} onChange={(event) => updateNode(node.id, { model: event.target.value })}>
                        <option value="">{isCloud ? '제공자 기본 모델' : '워커 기본 모델'}</option>
                        {[...(node.model && !options.includes(node.model) ? [node.model] : []), ...options].map((model) => <option key={model} value={model}>{model}</option>)}
                      </select>
                    </td>
                    <td className="setup-input-cell">
                      <small className={`input-summary${inputs.missing ? ' missing' : ''}`}>{isStart ? '시작 · ' : ''}{inputs.label}</small>
                      {inputs.hasText && <small className="text-preview" title={node.text_input}>텍스트 · {node.text_input!.trim()}</small>}
                      {nodeSlots.map((slot) => {
                        const count = slot.file_ids.length + slot.directory_ids.length
                        return <div className="slot-inline" key={slot.id}>
                          <span title={slot.format}>{slot.description}</span>
                          <small className={count ? 'ok' : 'empty'}>{count ? `${count}개 연결` : '비어 있음'}</small>
                          <button type="button" className="text-button" disabled={busy} onClick={() => startUpload(slot.id)}>올리기</button>
                        </div>
                      })}
                      {!nodeSlots.length && (node.needs_file || isStart) && <button type="button" className="text-button" onClick={() => createSlotFor(node)}>파일 슬롯 추가</button>}
                      {isStart && (inputs.missing || inputs.roleOnly) && <label className="toggle-row compact"><input type="checkbox" checked={!!node.allow_no_input} onChange={(event) => updateNode(node.id, { allow_no_input: event.target.checked })} />입력 없이 실행 허용</label>}
                      {isStart && inputs.missing && <Link className="text-button" to={`/services/${id}`}>텍스트 데이터는 편집 화면에서 입력</Link>}
                    </td>
                    <td>
                      {issues.length
                        ? issues.map((issue, index) => <span key={`${issue.code}-${index}`} className={`issue-dot ${issue.severity}`} title={issue.message}>{issue.severity === 'error' ? '오류' : '경고'}</span>)
                        : <span className="issue-dot ok">정상</span>}
                    </td>
                  </tr>
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <aside className="setup-side">
        <span className="eyebrow">VALIDATION</span>
        <h2>구성 검사</h2>
        <ValidationPanel validation={validation} nodeNames={nodeNames} onSelectNode={(nodeId) => document.getElementById(`setup-row-${nodeId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })} />
      </aside>
    </div>
    <input ref={uploadRef} className="inline-file-input" type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.pptx" onChange={onUpload} />
  </div>
}
