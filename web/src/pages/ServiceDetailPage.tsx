import { addEdge, Background, Connection, Controls, Edge, MarkerType, Node, ReactFlow, useEdgesState, useNodesState } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { DragEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, getDeviceDirectories } from '../api'
import AgentBlockNode, { categoryOf } from '../components/AgentBlockNode'
import { BLOCK_PRESETS, BlockPreset } from '../palette'
import { AgentNode, Device, Graph, Service, SharedDirectory, UploadedFile, WorkflowNode } from '../types'

const nodeTypes = { agent: AgentBlockNode }

function asAgents(graph: Graph): AgentNode[] {
  const legacyDirectories = new Map(
    graph.nodes.filter((node): node is Extract<WorkflowNode, { type: 'directory' }> => node.type === 'directory')
      .map((node) => [node.id, node.directory_id]),
  )
  return graph.nodes
    .filter((node): node is AgentNode => node.type === 'agent')
    .map((agent) => ({
      ...agent,
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

export default function ServiceDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [service, setService] = useState<Service | null>(null)
  const [agents, setAgents] = useState<Record<string, AgentNode>>({})
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [devices, setDevices] = useState<Device[]>([])
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

  const selectedAgent = selected ? agents[selected] : null
  const directoryById = useMemo(() => new Map(directories.map((directory) => [directory.id, directory])), [directories])
  const deviceById = useMemo(() => new Map(devices.map((device) => [device.id, device])), [devices])
  const uploadedFileById = useMemo(() => new Map(uploadedFiles.map((file) => [file.id, file])), [uploadedFiles])

  const nodeData = useCallback((agent: AgentNode) => ({
    label: agent.name,
    model: agent.model,
    workerName: agent.worker_id ? deviceById.get(agent.worker_id)?.name : undefined,
    directories: (agent.directory_ids ?? []).map((directoryId) => directoryById.get(directoryId)?.alias ?? `#${directoryId}`),
    files: (agent.uploaded_file_ids ?? []).map((fileId) => uploadedFileById.get(fileId)?.original_name ?? `#${fileId}`),
  }), [deviceById, directoryById, uploadedFileById])

  const applyAgents = useCallback((nextAgents: AgentNode[], graphEdges: Graph['edges'] = []) => {
    const positions = layout(nextAgents)
    setAgents(Object.fromEntries(nextAgents.map((agent) => [agent.id, agent])))
    setNodes(nextAgents.map((agent) => ({
      id: agent.id,
      type: 'agent',
      position: agent.position ?? positions[agent.id],
      data: nodeData(agent),
    })))
    setEdges(graphEdges.filter((edge) => edge.relation === 'workflow').map((edge) => ({
      ...edge,
      id: `${edge.source}-${edge.target}`,
      markerEnd: { type: MarkerType.ArrowClosed },
    })))
  }, [nodeData, setEdges, setNodes])

  useEffect(() => {
    async function load() {
      try {
        const [loadedService, loadedDevices, files] = await Promise.all([
          api.get<Service>(`/services/${id}`),
          api.get<Device[]>('/devices'),
          api.get<UploadedFile[]>('/files'),
        ])
        const directoryGroups = await Promise.all(loadedDevices.map((device) => getDeviceDirectories(device.id)))
        setService(loadedService)
        setSvcName(loadedService.name)
        setSvcDesc(loadedService.description)
        setDevices(loadedDevices)
        setDirectories(directoryGroups.flat())
        setUploadedFiles(files)
        const loadedAgents = asAgents(loadedService.graph)
        const positions = layout(loadedAgents)
        setAgents(Object.fromEntries(loadedAgents.map((agent) => [agent.id, agent])))
        setNodes(loadedAgents.map((agent) => ({ id: agent.id, type: 'agent', position: agent.position ?? positions[agent.id], data: {} })))
        setEdges(loadedService.graph.edges.filter((edge) => edge.relation === 'workflow').map((edge) => ({ ...edge, id: `${edge.source}-${edge.target}`, markerEnd: { type: MarkerType.ArrowClosed } })))
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : '불러오기 실패')
      }
    }
    load()
  }, [id, setEdges, setNodes])

  useEffect(() => {
    setNodes((current) => current.map((node) => ({ ...node, data: agents[node.id] ? nodeData(agents[node.id]) : node.data })))
  }, [agents, nodeData, setNodes])

  function currentGraph(): Graph {
    return {
      nodes: nodes.map((node) => ({ ...agents[node.id], position: node.position, directory_ids: agents[node.id].directory_ids ?? [], uploaded_file_ids: agents[node.id].uploaded_file_ids ?? [] })),
      edges: edges.map((edge) => ({ source: edge.source, target: edge.target, relation: 'workflow' as const })),
    }
  }

  function updateAgent(patch: Partial<AgentNode>) {
    if (!selectedAgent) return
    setAgents((current) => ({ ...current, [selectedAgent.id]: { ...selectedAgent, ...patch } }))
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
    setEdges((current) => addEdge({ ...connection, id: `${connection.source}-${connection.target}`, markerEnd: { type: MarkerType.ArrowClosed } }, current))
  }, [edges, setEdges])

  function deleteAgent() {
    if (!selected) return
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

  async function save(): Promise<boolean> {
    try {
      const updated = await api.put<Service>(`/services/${id}`, { name: svcName, description: svcDesc, graph: currentGraph() })
      setService(updated)
      setMessage('저장되었습니다.')
      return true
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '저장 실패')
      return false
    }
  }

  async function aiRevise(event: FormEvent) {
    event.preventDefault()
    setAiLoading(true)
    try {
      const result = await api.post<{ graph: Graph }>(`/services/${id}/revise`, { instruction: aiInstruction })
      applyAgents(asAgents(result.graph), result.graph.edges)
      setAiInstruction('')
      setMessage('AI 수정안을 적용했습니다. 저장해 주세요.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'AI 수정 실패') }
    finally { setAiLoading(false) }
  }

  if (!service) return <div className="page-loading">{error || 'Loading workflow...'}</div>

  return <div className="builder-page">
    <header className="builder-header">
      <div><div className="breadcrumb">M.A.R.S <span>/</span> Workflows <span>/</span> Builder</div><h1>{svcName}</h1><p>{svcDesc || 'Build and assign a distributed multi-agent workflow.'}</p></div>
      <div className="builder-header-actions"><button className="btn ghost" onClick={() => navigate('/services')}>All workflows</button><button className="btn" onClick={save}>Save changes</button></div>
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
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => setSelected(node.id)} onPaneClick={() => setSelected(null)} fitView><Background /><Controls /></ReactFlow>
      </div>
      <aside className="node-panel">
        {selectedAgent ? <>
          <div className="row spread"><h2 style={{ margin: 0 }}>에이전트 블록</h2><button className="btn sm danger" onClick={deleteAgent}>삭제</button></div>
          <label>이름</label><input value={selectedAgent.name} onChange={(event) => updateAgent({ name: event.target.value })} />
          <label>역할 프롬프트</label><textarea rows={5} value={selectedAgent.role_prompt} onChange={(event) => updateAgent({ role_prompt: event.target.value })} />
          <label>모델</label><input placeholder="비우면 Worker 기본값" value={selectedAgent.model} onChange={(event) => updateAgent({ model: event.target.value })} />
          <label>컴퓨팅 자원 (Worker)</label><select value={selectedAgent.worker_id ?? ''} onChange={(event) => updateAgent({ worker_id: event.target.value ? Number(event.target.value) : null })}><option value="">자동 배정</option>{devices.map((device) => <option key={device.id} value={device.id}>{device.name}{device.online ? ' · 온라인' : ' · 오프라인'}</option>)}</select>
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
          <h2 style={{ marginTop: 20 }}>Workflow execution</h2><p className="muted">Enter the run-specific prompt on a separate execution input screen.</p><button className="btn" style={{ marginTop: 12, width: '100%' }} onClick={async () => { if (await save()) navigate(`/services/${id}/run`) }}>Configure and run</button>
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
