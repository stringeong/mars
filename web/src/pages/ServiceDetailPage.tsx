import { addEdge, Background, Connection, Controls, Edge, MarkerType, Node, ReactFlow, useEdgesState, useNodesState } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { DragEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, getDeviceDirectories, getDeviceModels } from '../api'
import AgentBlockNode, { categoryOf } from '../components/AgentBlockNode'
import DeletableEdge from '../components/DeletableEdge'
import ValidationPanel from '../components/ValidationPanel'
import { BLOCK_PRESETS, BlockPreset } from '../palette'
import { AgentNode, Device, DeviceModels, Graph, InputSlot, Service, SharedDirectory, UploadedFile, ValidationResult, WorkflowNode } from '../types'
import { announceServiceRenamed, applyAutoFlags, blockingErrors, FlagExplanation, generationLabel, issuesByNode, onServiceRenamed } from '../workflow'

const nodeTypes = { agent: AgentBlockNode }
const edgeTypes = { deletable: DeletableEdge }

/** 편집기의 workflow 연결선. 선택하면 삭제(×) 버튼이 나온다. */
function toFlowEdge(source: string, target: string): Edge {
  return { id: `${source}-${target}`, source, target, type: 'deletable', markerEnd: { type: MarkerType.ArrowClosed } }
}

// 저장 전까지 되돌릴 수 있는 구조 변경 기록(연결·블록 추가/삭제, 체크박스)
type BuilderSnapshot = { agents: Record<string, AgentNode>; nodes: Node[]; edges: Edge[] }
const UNDO_LIMIT = 50


const CLOUD_MODELS = {
  openai: ['gpt-5-mini', 'gpt-5', 'gpt-4.1-mini', 'gpt-4.1'],
  anthropic: ['claude-sonnet-4-5', 'claude-opus-4-1', 'claude-haiku-3-5'],
  gemini: ['gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-3.5-flash-lite', 'gemini-2.5-pro'],
} as const

function asAgents(graph: Graph): AgentNode[] {
  const legacyDirectories = new Map(
    graph.nodes.filter((node): node is Extract<WorkflowNode, { type: 'directory' }> => node.type === 'directory')
      .map((node) => [node.id, node.directory_id]),
  )
  return graph.nodes
    // Legacy generated services omitted `type`; the server treats them as agents.
    .filter((node): node is AgentNode => !node.type || node.type === 'agent')
    .map((agent) => ({
      ...agent,
      type: 'agent',
      directory_ids: agent.directory_ids ?? graph.edges
        .filter((edge) => edge.relation === 'directory' && edge.target === agent.id)
        .map((edge) => legacyDirectories.get(edge.source))
        .filter((id): id is number => id !== undefined),
      uploaded_file_ids: agent.uploaded_file_ids ?? [],
    }))
}

function layout(agents: AgentNode[]): Record<string, { x: number; y: number }> {
  return Object.fromEntries(agents.map((agent, index) => [agent.id, { x: 60 + (index % 3) * 280, y: 70 + Math.floor(index / 3) * 230 }]))
}

/** 자동으로 정해진 값을 보여주고, 바꾸면 '직접 지정'으로 남긴다. */
function FlagToggle({ label, checked, explanation, onChange, onReset }: {
  label: string
  checked: boolean
  explanation?: FlagExplanation
  onChange: (checked: boolean) => void
  onReset: () => void
}) {
  return <div className="flag-toggle">
    <label className="toggle-row"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />{label}<span className={`flag-source ${explanation?.manual ? 'manual' : 'auto'}`}>{explanation?.manual ? '직접 지정' : '자동'}</span></label>
    {explanation && <small className="flag-reason">{explanation.reason}</small>}
    {explanation?.manual && <button type="button" className="text-button flag-reset" onClick={onReset}>자동으로 되돌리기</button>}
  </div>
}

export default function ServiceDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [service, setService] = useState<Service | null>(null)
  const [agents, setAgents] = useState<Record<string, AgentNode>>({})
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [deviceModels, setDeviceModels] = useState<Record<number, DeviceModels>>({})
  const [syncVersion, setSyncVersion] = useState(0)
  const [syncing, setSyncing] = useState(false)
  const [directories, setDirectories] = useState<SharedDirectory[]>([])
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [fileUploading, setFileUploading] = useState(false)
  const [fileLibraryOpen, setFileLibraryOpen] = useState(false)
  const [draftFileIds, setDraftFileIds] = useState<number[]>([])
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [svcName, setSvcName] = useState('')
  const [svcDesc, setSvcDesc] = useState('')
  const [aiInstruction, setAiInstruction] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [inputSlots, setInputSlots] = useState<InputSlot[]>([])
  const [validation, setValidation] = useState<ValidationResult | null>(null)

  const selectedAgent = selected ? agents[selected] : null
  const issueMap = useMemo(() => issuesByNode(validation), [validation])
  const selectedIssues = selected ? issueMap.get(selected) ?? [] : []
  const nodeNames = useMemo(() => Object.fromEntries(Object.values(agents).map((agent) => [agent.id, agent.name])), [agents])
  const directoryById = useMemo(() => new Map(directories.map((directory) => [directory.id, directory])), [directories])
  const deviceById = useMemo(() => new Map(devices.map((device) => [device.id, device])), [devices])
  const uploadedFileById = useMemo(() => new Map(uploadedFiles.map((file) => [file.id, file])), [uploadedFiles])
  const selectedProvider = selectedAgent?.provider || 'ollama'
  const modelOptions = useMemo(() => {
    if (selectedProvider !== 'ollama') return [...CLOUD_MODELS[selectedProvider]]
    const relevantDevices = selectedAgent?.worker_id
      ? devices.filter((device) => device.id === selectedAgent.worker_id)
      : devices.filter((device) => device.online)
    return [...new Set(relevantDevices.flatMap((device) => deviceModels[device.id]?.models ?? []))].sort()
  }, [devices, deviceModels, selectedAgent?.worker_id, selectedProvider])
  const visibleModelOptions = selectedAgent?.model && !modelOptions.includes(selectedAgent.model)
    ? [selectedAgent.model, ...modelOptions]
    : modelOptions
  const selectedDeviceModelInfo = selectedAgent?.worker_id ? deviceModels[selectedAgent.worker_id] : undefined

  const nodeData = useCallback((agent: AgentNode) => {
    const issues = issueMap.get(agent.id) ?? []
    return {
    label: agent.name,
    model: agent.model,
    final: agent.final,
    issueLevel: issues.some((issue) => issue.severity === 'error') ? 'error' : issues.length ? 'warning' : undefined,
    issueCount: issues.length,
    issueMessages: issues.map((issue) => issue.message).join('\n'),
    workerName: agent.worker_id ? deviceById.get(agent.worker_id)?.name : undefined,
    directories: (agent.directory_ids ?? []).map((directoryId) => directoryById.get(directoryId)?.alias ?? `#${directoryId}`),
    files: [
      ...(agent.uploaded_file_ids ?? []),
      ...inputSlots.filter((slot) => (agent.input_slot_ids ?? []).includes(slot.id)).flatMap((slot) => slot.file_ids),
    ].map((fileId) => uploadedFileById.get(fileId)?.original_name ?? `#${fileId}`),
    }
  }, [deviceById, directoryById, inputSlots, issueMap, uploadedFileById])

  const applyAgents = useCallback((nextAgents: AgentNode[], graphEdges: Graph['edges'] = []) => {
    const positions = layout(nextAgents)
    setAgents(Object.fromEntries(nextAgents.map((agent) => [agent.id, agent])))
    setNodes(nextAgents.map((agent) => ({
      id: agent.id,
      type: 'agent',
      position: agent.position ?? positions[agent.id],
      data: nodeData(agent),
    })))
    setEdges(graphEdges.filter((edge) => !edge.relation || edge.relation === 'workflow').map((edge) => toFlowEdge(edge.source, edge.target)))
  }, [nodeData, setEdges, setNodes])

  useEffect(() => {
    async function load() {
      try {
        setSyncing(true)
        const [loadedService, loadedDevices, files] = await Promise.all([
          api.get<Service>(`/services/${id}`),
          api.get<Device[]>('/devices'),
          api.get<UploadedFile[]>('/files'),
        ])
        const directoryGroups = await Promise.all(loadedDevices.map((device) => getDeviceDirectories(device.id)))
        const modelGroups = await Promise.all(loadedDevices.map((device) => getDeviceModels(device.id)))
        setService(loadedService)
        setSvcName(loadedService.name)
        setSvcDesc(loadedService.description)
        setDevices(loadedDevices)
        setDeviceModels(Object.fromEntries(modelGroups.map((item) => [item.device_id, item])))
        setDirectories(directoryGroups.flat())
        setUploadedFiles(files)
        setInputSlots(loadedService.graph.input_slots ?? [])
        const loadedAgents = asAgents(loadedService.graph)
        const positions = layout(loadedAgents)
        setAgents(Object.fromEntries(loadedAgents.map((agent) => [agent.id, agent])))
        setNodes(loadedAgents.map((agent) => ({ id: agent.id, type: 'agent', position: agent.position ?? positions[agent.id], data: {} })))
        setEdges(loadedService.graph.edges.filter((edge) => !edge.relation || edge.relation === 'workflow').map((edge) => toFlowEdge(edge.source, edge.target)))
        clearHistory()
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : '불러오기 실패')
      } finally {
        setSyncing(false)
      }
    }
    load()
  }, [id, setEdges, setNodes, syncVersion])

  useEffect(() => {
    setNodes((current) => current.map((node) => ({ ...node, data: agents[node.id] ? nodeData(agents[node.id]) : node.data })))
  }, [agents, nodeData, setNodes])

  // 사이드바에서 이름을 바꾸면 이 화면의 이름도 바꿔 둔다 (저장할 때 예전 이름으로 덮어쓰지 않도록)
  useEffect(() => onServiceRenamed((renamed) => {
    if (String(renamed.id) !== id) return
    setSvcName(renamed.name)
    setService((current) => (current ? { ...current, name: renamed.name } : current))
  }), [id])

  function currentGraph(): Graph {
    return {
      nodes: nodes.filter((node) => agents[node.id]).map((node) => ({ ...agents[node.id], position: node.position, directory_ids: agents[node.id].directory_ids ?? [], uploaded_file_ids: agents[node.id].uploaded_file_ids ?? [] })),
      edges: edges.map((edge) => ({ source: edge.source, target: edge.target, relation: 'workflow' as const })),
      input_slots: inputSlots,
    }
  }

  // 연결·블록·직접 지정 값이 바뀌면 최종 블록과 파일 필요 기본값을 다시 계산한다 (직접 지정한 값은 그대로)
  const flagInputsKey = useMemo(() => JSON.stringify({
    agents: Object.values(agents).map((agent) => [agent.id, agent.name, agent.final_hint, agent.needs_file_hint, agent.final_manual && agent.final, agent.final_manual, agent.needs_file_manual && agent.needs_file, agent.needs_file_manual]),
    edges: edges.map((edge) => [edge.source, edge.target]),
  }), [agents, edges])
  const flagReasons = useMemo(() => applyAutoFlags(Object.values(agents), edges).reasons, [flagInputsKey])

  useEffect(() => {
    const current = Object.values(agents)
    if (!current.length) return
    const next = applyAutoFlags(current, edges).agents
    if (next.some((agent) => agent.final !== !!agents[agent.id]?.final || agent.needs_file !== !!agents[agent.id]?.needs_file)) {
      setAgents(Object.fromEntries(next.map((agent) => [agent.id, agent])))
    }
  }, [flagInputsKey])

  // 블록 위치를 뺀 구성이 바뀌면 잠시 뒤 서버에서 다시 검사한다
  const graphKey = useMemo(() => JSON.stringify({
    agents: Object.values(agents).map(({ position: _position, ...agent }) => agent),
    edges: edges.map((edge) => [edge.source, edge.target]),
    inputSlots,
  }), [agents, edges, inputSlots])

  useEffect(() => {
    if (!service || !Object.keys(agents).length) return
    const timer = window.setTimeout(() => {
      api.post<ValidationResult>(`/services/${id}/validate`, { graph: currentGraph() }).then(setValidation).catch(() => {})
    }, 400)
    return () => window.clearTimeout(timer)
  }, [graphKey, service?.id])

  function updateAgent(patch: Partial<AgentNode>) {
    if (!selectedAgent) return
    setAgents((current) => ({ ...current, [selectedAgent.id]: { ...selectedAgent, ...patch } }))
  }

  // ---------- 되돌리기 (저장 전까지) ----------
  const historyRef = useRef<BuilderSnapshot[]>([])
  const [historySize, setHistorySize] = useState(0)
  const latestRef = useRef<BuilderSnapshot>({ agents, nodes, edges })
  latestRef.current = { agents, nodes, edges }

  // 구조를 바꾸기 직전에 부른다. 글자 입력은 브라우저 기본 되돌리기를 쓴다.
  const pushHistory = useCallback(() => {
    historyRef.current = [...historyRef.current.slice(-(UNDO_LIMIT - 1)), latestRef.current]
    setHistorySize(historyRef.current.length)
  }, [])

  function clearHistory() {
    historyRef.current = []
    setHistorySize(0)
  }

  const undo = useCallback(() => {
    const previous = historyRef.current.pop()
    if (!previous) return
    setHistorySize(historyRef.current.length)
    setAgents(previous.agents)
    setNodes(previous.nodes)
    setEdges(previous.edges)
    setSelected((current) => (current && previous.agents[current] ? current : null))
    setMessage('마지막 변경을 되돌렸습니다.')
  }, [setEdges, setNodes])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey) || event.shiftKey || event.key.toLowerCase() !== 'z') return
      // 입력 칸 안에서는 브라우저의 글자 되돌리기를 그대로 쓴다
      if ((event.target as HTMLElement | null)?.closest('input, textarea, select, [contenteditable="true"]')) return
      event.preventDefault()
      undo()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [undo])

  function changeFlags(patch: Partial<AgentNode>) {
    pushHistory()
    updateAgent(patch)
  }

  // 패널의 연결 목록에서 지울 때. 캔버스에서 지울 때는 onBeforeDelete가 기록을 남긴다.
  function removeConnection(edgeId: string) {
    pushHistory()
    setEdges((current) => current.filter((edge) => edge.id !== edgeId))
    setMessage('연결을 삭제했습니다. 저장하기 전까지 Ctrl/Cmd+Z로 되돌릴 수 있습니다.')
  }

  // 최종 블록은 하나만 둔다. 직접 지정하면 다른 블록의 직접 지정은 풀고 자동 규칙에 맡긴다.
  function setFinal(checked: boolean) {
    if (!selectedAgent) return
    pushHistory()
    setAgents((current) => Object.fromEntries(Object.entries(current).map(([agentId, agent]) => [
      agentId,
      agentId === selectedAgent.id ? { ...agent, final: checked, final_manual: true }
        : checked && agent.final_manual ? { ...agent, final_manual: false } : agent,
    ])))
  }

  function addAgent(preset: BlockPreset, position?: { x: number; y: number }) {
    const agent: AgentNode = {
      id: `agent_${Date.now()}`,
      type: 'agent',
      name: preset.name,
      role_prompt: preset.role_prompt,
      model: '',
      worker_id: null,
      directory_ids: [],
      uploaded_file_ids: [],
    }
    pushHistory()
    setAgents((current) => ({ ...current, [agent.id]: agent }))
    setNodes((current) => [...current, { id: agent.id, type: 'agent', position: position ?? { x: 80, y: 80 + current.length * 35 }, data: nodeData(agent) }])
    setSelected(agent.id)
  }

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return
    if (edges.some((edge) => edge.source === connection.source && edge.target === connection.target)) {
      setError('이미 연결된 에이전트입니다.')
      return
    }
    pushHistory()
    setEdges((current) => addEdge(toFlowEdge(connection.source!, connection.target!), current))
  }, [edges, pushHistory, setEdges])

  function deleteAgent() {
    if (!selected) return
    pushHistory()
    setAgents((current) => Object.fromEntries(Object.entries(current).filter(([agentId]) => agentId !== selected)))
    setNodes((current) => current.filter((node) => node.id !== selected))
    setEdges((current) => current.filter((edge) => edge.source !== selected && edge.target !== selected))
    setSelected(null)
  }

  function openFileLibrary() {
    setDraftFileIds([...(selectedAgent?.uploaded_file_ids ?? [])])
    setFileLibraryOpen(true)
  }

  function applyFileLibrarySelection() {
    updateAgent({ uploaded_file_ids: draftFileIds })
    setFileLibraryOpen(false)
  }

  async function uploadForSelectedAgent(files: FileList | null) {
    if (!selected || !files?.length) return
    setFileUploading(true)
    setError("")
    try {
      const uploaded: UploadedFile[] = []
      for (const file of Array.from(files)) {
        const form = new FormData()
        form.append("file", file)
        uploaded.push(await api.upload<UploadedFile>("/files", form))
      }
      setUploadedFiles((current) => {
        const byId = new Map([...uploaded, ...current].map((file) => [file.id, file]))
        return [...byId.values()]
      })
      const uploadedIds = uploaded.map((file) => file.id)
      setAgents((current) => {
        const agent = current[selected]
        if (!agent) return current
        return {
          ...current,
          [selected]: {
            ...agent,
            uploaded_file_ids: [...new Set([...(agent.uploaded_file_ids ?? []), ...uploadedIds])],
          },
        }
      })
      setMessage(String(uploaded.length) + "개 파일을 업로드하고 현재 에이전트에 첨부했습니다. 저장해 주세요.")
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "파일 업로드 실패")
    } finally {
      setFileUploading(false)
      if (uploadInputRef.current) uploadInputRef.current.value = ""
    }
  }

  async function save(): Promise<Service | null> {
    try {
      const updated = await api.put<Service>(`/services/${id}`, { name: svcName, description: svcDesc, graph: currentGraph() })
      if (updated.name !== service?.name) announceServiceRenamed(updated.id, updated.name)
      setService(updated)
      setValidation(updated.validation ?? null)
      setError('')
      clearHistory()
      const issueCount = (updated.validation?.errors.length ?? 0) + (updated.validation?.warnings.length ?? 0)
      setMessage(issueCount ? `저장되었습니다. 구성 검사에서 문제 ${issueCount}개가 발견되었습니다.` : '저장되었습니다.')
      return updated
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '저장 실패')
      return null
    }
  }

  async function configureAndRun() {
    const updated = await save()
    if (!updated) return
    // 실행 프롬프트로 풀리는 '입력 없음' 오류만 남았다면 실행 화면으로 넘어간다
    const blocking = blockingErrors(updated.validation)
    if (blocking.length) {
      setError(`실행하기 전에 오류 ${blocking.length}개를 고쳐 주세요: ${blocking[0].message}`)
      return
    }
    navigate(`/services/${id}/run`)
  }

  async function aiRevise(event: FormEvent) {
    event.preventDefault()
    setAiLoading(true)
    try {
      const result = await api.post<{ graph: Graph }>(`/services/${id}/revise`, { instruction: aiInstruction })
      pushHistory()
      applyAgents(asAgents(result.graph), result.graph.edges)
      setAiInstruction('')
      setMessage('AI 수정안을 적용했습니다. 저장해 주세요.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'AI 수정 실패') }
    finally { setAiLoading(false) }
  }

  if (!service) return <div className="page-loading">{error || 'Loading workflow...'}</div>

  return <div className="builder-page">
    <header className="builder-header">
      <div><div className="breadcrumb">M.A.R.S <span>/</span> Workflows <span>/</span> Builder</div><h1>{svcName}</h1><p>{svcDesc || 'Build and assign a distributed multi-agent workflow.'}</p><div className="generation-badge"><span>생성 모델</span><strong>{generationLabel(service.generation_info)}</strong></div></div>
      <div className="builder-header-actions"><button className="btn ghost" disabled={!historySize} onClick={undo} title="Ctrl/Cmd+Z">↶ 되돌리기{historySize ? ` (${historySize})` : ''}</button><button className="btn ghost" onClick={async () => { if (await save()) navigate(`/services/${id}/setup`) }}>설정 확인 표</button><button className="btn ghost" disabled={syncing} onClick={() => { if (confirm('서버의 최신 워크플로우와 Worker 정보로 다시 불러올까요? 저장하지 않은 변경은 사라집니다.')) setSyncVersion((version) => version + 1) }}>{syncing ? '동기화 중…' : '↻ 서버와 재동기화'}</button><button className="btn ghost" onClick={() => navigate('/services')}>All workflows</button><button className="btn" onClick={save}>Save changes</button></div>
    </header>
    {message && <div style={{ color: 'var(--success)', marginBottom: 8 }}>{message}</div>}
    {error && <div className="error">{error}</div>}
    <form className="ai-bar" onSubmit={aiRevise}>
      <span className="ai-bar-label">AI로 수정</span>
      <input value={aiInstruction} onChange={(event) => setAiInstruction(event.target.value)} placeholder="예: 검토 에이전트를 분석 뒤에 추가해줘" required minLength={2} />
      <button className="btn sm" disabled={aiLoading}>{aiLoading ? '수정 중...' : '적용'}</button>
    </form>
    <div className="builder3 builder-workspace">
      <aside className="palette">
        <div className="palette-title">에이전트 블록</div><div className="palette-hint">드래그하거나 클릭해 추가</div>
        {BLOCK_PRESETS.map((preset) => { const category = categoryOf(preset.name); return <div key={preset.name} className="palette-block" style={{ borderColor: category.color, background: category.bg }} draggable onDragStart={(event) => event.dataTransfer.setData('application/mars-agent', JSON.stringify(preset))} onClick={() => addAgent(preset)}><span className="palette-block-tag" style={{ background: category.color }}>{category.tag}</span><div className="palette-block-name">{preset.name}</div><div className="palette-block-hint">{preset.hint}</div></div> })}
      </aside>
      <div className="flow-wrap" onDragOver={(event) => event.preventDefault()} onDrop={(event: DragEvent) => { event.preventDefault(); const raw = event.dataTransfer.getData('application/mars-agent'); if (raw) addAgent(JSON.parse(raw), { x: event.nativeEvent.offsetX - 100, y: event.nativeEvent.offsetY - 50 }) }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => setSelected(node.id)}
          onPaneClick={() => setSelected(null)}
          deleteKeyCode={['Delete', 'Backspace']}
          onBeforeDelete={async () => { pushHistory(); return true }}
          onEdgesDelete={(deleted) => setMessage(`연결 ${deleted.length}개를 삭제했습니다. 저장하기 전까지 Ctrl/Cmd+Z로 되돌릴 수 있습니다.`)}
          onNodesDelete={(deleted) => {
            // 키보드로 블록을 지우면 블록 설정도 함께 지운다
            const removed = new Set(deleted.map((node) => node.id))
            setAgents((current) => Object.fromEntries(Object.entries(current).filter(([agentId]) => !removed.has(agentId))))
            setSelected((current) => (current && removed.has(current) ? null : current))
          }}
          fitView
        ><Background /><Controls /></ReactFlow>
      </div>
      <aside className="node-panel">
        {selectedAgent ? <>
          <div className="row spread"><h2 style={{ margin: 0 }}>에이전트 블록</h2><button className="btn sm danger" onClick={deleteAgent}>삭제</button></div>
          {selectedIssues.length > 0 && <ul className="validation-list node-issues">{selectedIssues.map((issue, index) => <li key={`${issue.code}-${index}`} className={issue.severity}>{issue.message}</li>)}</ul>}
          <label>이름</label><input value={selectedAgent.name} onChange={(event) => updateAgent({ name: event.target.value })} />
          <FlagToggle label="최종 블록 (출력이 실행 결과가 됨)" checked={!!selectedAgent.final} explanation={flagReasons[selectedAgent.id]?.final} onChange={setFinal} onReset={() => changeFlags({ final_manual: false })} />
          <FlagToggle label="사용자 파일 필요" checked={!!selectedAgent.needs_file} explanation={flagReasons[selectedAgent.id]?.needsFile} onChange={(checked) => changeFlags({ needs_file: checked, needs_file_manual: true })} onReset={() => changeFlags({ needs_file_manual: false })} />
          <label>연결</label>
          <div className="connection-list">
            {([['incoming', '들어오는 연결', edges.filter((edge) => edge.target === selectedAgent.id)], ['outgoing', '나가는 연결', edges.filter((edge) => edge.source === selectedAgent.id)]] as const).map(([kind, title, list]) => <div className="connection-group" key={kind}>
              <span className="connection-title">{title} {list.length}</span>
              {list.map((edge) => {
                const other = agents[kind === 'incoming' ? edge.source : edge.target]
                return <div className="connection-item" key={edge.id}>
                  <span>{kind === 'incoming' ? '← ' : '→ '}{other?.name ?? (kind === 'incoming' ? edge.source : edge.target)}</span>
                  <button type="button" aria-label={`${other?.name ?? ''} 연결 삭제`} title="연결 삭제" onClick={() => removeConnection(edge.id)}>×</button>
                </div>
              })}
              {!list.length && <small className="muted">없음</small>}
            </div>)}
          </div>
          {inputSlots.filter((slot) => (selectedAgent.input_slot_ids ?? []).includes(slot.id)).map((slot) => <div className="slot-inline node-slot" key={slot.id}><span title={slot.format}>파일 슬롯 · {slot.description}</span><small className={slot.file_ids.length + slot.directory_ids.length ? 'ok' : 'empty'}>{slot.file_ids.length + slot.directory_ids.length ? `${slot.file_ids.length + slot.directory_ids.length}개 연결` : '비어 있음'}</small></div>)}
          <label>역할 프롬프트</label><textarea rows={5} value={selectedAgent.role_prompt} onChange={(event) => updateAgent({ role_prompt: event.target.value })} />
          <label>실행 위치</label><select value={selectedAgent.provider || 'ollama'} onChange={(event) => { const provider = event.target.value as 'ollama' | 'openai' | 'anthropic' | 'gemini'; updateAgent({ provider, executor: provider === 'ollama' ? 'local' : 'cloud', worker_id: provider === 'ollama' ? selectedAgent.worker_id : null, model: '' }) }}><option value="ollama">Local Worker · Ollama</option><option value="openai">Cloud · OpenAI</option><option value="anthropic">Cloud · Anthropic</option><option value="gemini">Cloud · Google Gemini</option></select>
          <label>컴퓨팅 자원 (Worker)</label><select disabled={selectedProvider !== 'ollama'} value={selectedAgent.worker_id ?? ''} onChange={(event) => updateAgent({ worker_id: event.target.value ? Number(event.target.value) : null, model: '' })}><option value="">자동 배정</option>{devices.map((device) => <option key={device.id} value={device.id}>{device.name}{device.online ? ' · 온라인' : ' · 오프라인'}</option>)}</select>
          <label>모델</label><select value={selectedAgent.model} onChange={(event) => updateAgent({ model: event.target.value })}>
            <option value="">{selectedProvider === 'ollama' ? selectedDeviceModelInfo?.default_model ? `Worker 기본 모델 · ${selectedDeviceModelInfo.default_model}` : 'Worker 기본 모델' : '공급자 기본 모델'}</option>
            {visibleModelOptions.map((model) => <option value={model} key={model}>{model}</option>)}
          </select>
          {selectedProvider === 'ollama' && !selectedAgent.worker_id && <small className="muted">Worker를 선택하면 해당 기기에 설치된 모델만 표시됩니다. 자동 배정은 온라인 Worker 모델의 합집합입니다.</small>}
          {selectedProvider === 'ollama' && selectedAgent.worker_id && !modelOptions.length && <small className="muted">선택한 Worker가 설치된 Ollama 모델을 아직 서버에 보고하지 않았습니다. Worker 실행 상태를 확인한 뒤 재동기화하세요.</small>}
          {selectedDeviceModelInfo?.synced_at && <small className="muted">모델 동기화: {new Date(selectedDeviceModelInfo.synced_at).toLocaleString()}</small>}
          <label>공유 디렉터리</label>
          <div className="resource-picker directory-resource-picker">
            {directories.length ? directories.map((directory) => <label key={directory.id} className="resource-check"><input type="checkbox" checked={(selectedAgent.directory_ids ?? []).includes(directory.id)} onChange={(event) => updateAgent({ directory_ids: event.target.checked ? [...(selectedAgent.directory_ids ?? []), directory.id] : (selectedAgent.directory_ids ?? []).filter((directoryId) => directoryId !== directory.id) })} /><span><strong>{directory.alias}</strong><small>{directory.local_path}</small></span></label>) : <span className="muted">등록된 공유 디렉터리가 없습니다.</span>}
          </div>
          <div className="uploaded-file-picker">
            <div className="uploaded-file-heading"><strong>첨부 파일</strong><div className="file-picker-actions"><button type="button" className="btn sm ghost" disabled={fileUploading} onClick={() => uploadInputRef.current?.click()}>{fileUploading ? '업로드 중…' : '새 파일 업로드'}</button><button type="button" className="btn sm ghost" onClick={openFileLibrary}>기존 파일 선택</button></div><input ref={uploadInputRef} className="inline-file-input" type="file" multiple accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.pptx" onChange={(event) => uploadForSelectedAgent(event.target.files)} /></div>
            <small className="file-picker-help">현재 에이전트가 실행할 때 우선 읽는 파일입니다.</small>
            <div className="selected-file-list">
              {(selectedAgent.uploaded_file_ids ?? []).map((fileId) => { const file = uploadedFileById.get(fileId); return <div className="selected-file-chip" key={fileId}><span><strong>{file?.original_name ?? '삭제된 파일'}</strong><small>{file ? file.size_bytes.toLocaleString() + ' bytes' : '#' + fileId}</small></span><button type="button" aria-label="첨부 해제" onClick={() => updateAgent({ uploaded_file_ids: (selectedAgent.uploaded_file_ids ?? []).filter((id) => id !== fileId) })}>×</button></div> })}
              {!(selectedAgent.uploaded_file_ids ?? []).length && <span className="muted">선택된 파일이 없습니다.</span>}
            </div>
          </div>
        </> : <>
          <h2>서비스 정보</h2><label>이름</label><input value={svcName} onChange={(event) => setSvcName(event.target.value)} /><label>설명</label><textarea rows={3} value={svcDesc} onChange={(event) => setSvcDesc(event.target.value)} />
          <h2 style={{ marginTop: 20 }}>구성 검사</h2>
          <ValidationPanel validation={validation} nodeNames={nodeNames} onSelectNode={setSelected} />
          <h2 style={{ marginTop: 20 }}>Workflow execution</h2><p className="muted">Enter the run-specific prompt on a separate execution input screen.</p><button className="btn" style={{ marginTop: 12, width: '100%' }} onClick={configureAndRun}>Configure and run</button>
        </>}
      </aside>
    </div>
    {fileLibraryOpen && <div className="file-library-modal-backdrop" role="presentation" onMouseDown={() => setFileLibraryOpen(false)}>
      <section className="file-library-modal" role="dialog" aria-modal="true" aria-labelledby="file-library-title" onMouseDown={(event) => event.stopPropagation()}>
        <header><div><span className="eyebrow">FILE LIBRARY</span><h2 id="file-library-title">기존 파일 선택</h2></div><button type="button" className="modal-close" aria-label="닫기" onClick={() => setFileLibraryOpen(false)}>×</button></header>
        <p>이 에이전트가 실행할 때 읽을 파일을 선택하세요.</p>
        <div className="modal-file-list">
          {uploadedFiles.map((file) => <label className="modal-file-item" key={file.id}><input type="checkbox" checked={draftFileIds.includes(file.id)} onChange={(event) => setDraftFileIds((current) => event.target.checked ? [...current, file.id] : current.filter((id) => id !== file.id))} /><span><strong>{file.original_name}</strong><small>{file.size_bytes.toLocaleString()} bytes · {new Date(file.created_at).toLocaleDateString()}</small></span></label>)}
          {!uploadedFiles.length && <div className="modal-file-empty">업로드된 파일이 없습니다. 먼저 새 파일을 업로드해 주세요.</div>}
        </div>
        <footer><span>{draftFileIds.length}개 선택</span><div><button type="button" className="btn sm ghost" onClick={() => setFileLibraryOpen(false)}>취소</button><button type="button" className="btn sm" onClick={applyFileLibrarySelection}>선택 적용</button></div></footer>
      </section>
    </div>}
  </div>
}
