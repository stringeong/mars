import {
  addEdge,
  Background,
  Connection,
  Controls,
  Edge,
  MarkerType,
  Node,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { DragEvent, FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import AgentBlockNode, { categoryOf } from '../components/AgentBlockNode'
import DeletableEdge from '../components/DeletableEdge'
import { BLOCK_PRESETS, BlockPreset } from '../palette'
import { AgentNode, Execution, Graph, Service } from '../types'

const nodeTypes = { agent: AgentBlockNode }
const edgeTypes = { del: DeletableEdge }

/** 그래프의 노드를 계층(위상 순서)별로 자동 배치한다. */
function layoutPositions(graph: Graph): Record<string, { x: number; y: number }> {
  const level: Record<string, number> = {}
  const parents: Record<string, string[]> = {}
  graph.nodes.forEach((n) => (parents[n.id] = []))
  graph.edges.forEach((e) => parents[e.target]?.push(e.source))

  const resolve = (id: string, seen: Set<string>): number => {
    if (level[id] !== undefined) return level[id]
    if (seen.has(id)) return 0
    seen.add(id)
    const ps = parents[id] ?? []
    level[id] = ps.length === 0 ? 0 : Math.max(...ps.map((p) => resolve(p, seen))) + 1
    return level[id]
  }
  graph.nodes.forEach((n) => resolve(n.id, new Set()))

  const counts: Record<number, number> = {}
  const pos: Record<string, { x: number; y: number }> = {}
  graph.nodes.forEach((n) => {
    const lv = level[n.id]
    counts[lv] = (counts[lv] ?? 0) + 1
    pos[n.id] = { x: lv * 240 + 40, y: (counts[lv] - 1) * 130 + 40 }
  })
  return pos
}

interface Snapshot {
  nodes: Node[]
  edges: Edge[]
  agents: Record<string, AgentNode>
}

export default function ServiceDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [service, setService] = useState<Service | null>(null)
  const [svcName, setSvcName] = useState('')
  const [svcDesc, setSvcDesc] = useState('')
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [agents, setAgents] = useState<Record<string, AgentNode>>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [runPrompt, setRunPrompt] = useState('')
  const [aiInstruction, setAiInstruction] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [, setHistVersion] = useState(0)

  const rfInstance = useRef<any>(null)
  const undoStack = useRef<Snapshot[]>([])
  const redoStack = useRef<Snapshot[]>([])
  // 콜백들이 항상 최신 상태를 보도록 ref에 미러링
  const stateRef = useRef<Snapshot>({ nodes: [], edges: [], agents: {} })
  stateRef.current = { nodes, edges, agents }

  const clone = (s: Snapshot): Snapshot => JSON.parse(JSON.stringify(s))

  const pushHistory = useCallback(() => {
    undoStack.current.push(clone(stateRef.current))
    if (undoStack.current.length > 50) undoStack.current.shift()
    redoStack.current = []
    setHistVersion((v) => v + 1)
  }, [])

  const deleteEdge = useCallback((edgeId: string) => {
    pushHistory()
    setEdges((eds) => eds.filter((e) => e.id !== edgeId))
  }, [pushHistory, setEdges])
  const deleteEdgeRef = useRef(deleteEdge)
  deleteEdgeRef.current = deleteEdge

  const makeEdge = useCallback((source: string, target: string): Edge => ({
    id: `${source}-${target}`,
    source,
    target,
    type: 'del',
    markerEnd: { type: MarkerType.ArrowClosed },
    data: { onDelete: (eid: string) => deleteEdgeRef.current(eid) },
  }), [])

  const applySnapshot = useCallback((snap: Snapshot) => {
    setNodes(snap.nodes)
    setEdges(snap.edges.map((e) => ({ ...e, data: { onDelete: (eid: string) => deleteEdgeRef.current(eid) } })))
    setAgents(snap.agents)
    setSelected(null)
  }, [setNodes, setEdges])

  const undo = useCallback(() => {
    const snap = undoStack.current.pop()
    if (!snap) return
    redoStack.current.push(clone(stateRef.current))
    applySnapshot(snap)
    setHistVersion((v) => v + 1)
  }, [applySnapshot])

  const redo = useCallback(() => {
    const snap = redoStack.current.pop()
    if (!snap) return
    undoStack.current.push(clone(stateRef.current))
    applySnapshot(snap)
    setHistVersion((v) => v + 1)
  }, [applySnapshot])

  useEffect(() => {
    api.get<Service>(`/services/${id}`).then((s) => {
      setService(s)
      setSvcName(s.name)
      setSvcDesc(s.description)
      const positions = layoutPositions(s.graph)
      const agentMap: Record<string, AgentNode> = {}
      s.graph.nodes.forEach((n) => (agentMap[n.id] = n))
      setAgents(agentMap)
      setNodes(
        s.graph.nodes.map((n) => ({
          id: n.id,
          type: 'agent',
          position: n.position ?? positions[n.id],
          data: { label: n.name, model: n.model },
        })),
      )
      setEdges(s.graph.edges.map((e) => makeEdge(e.source, e.target)))
    }).catch((e) => setError(e.message))
  }, [id])

  // Cmd/Ctrl+Z 되돌리기, Shift+Cmd/Ctrl+Z 다시 실행
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        const target = e.target as HTMLElement
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return
        e.preventDefault()
        if (e.shiftKey) redo()
        else undo()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [undo, redo])

  const onConnect = useCallback((conn: Connection) => {
    if (!conn.source || !conn.target) return
    pushHistory()
    setEdges((eds) => addEdge(makeEdge(conn.source!, conn.target!), eds))
  }, [pushHistory, setEdges, makeEdge])

  const selectedAgent = selected ? agents[selected] : null

  function updateAgent(patch: Partial<AgentNode>) {
    if (!selected) return
    setAgents((prev) => ({ ...prev, [selected]: { ...prev[selected], ...patch } }))
    if (patch.name !== undefined || patch.model !== undefined) {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === selected
            ? {
                ...n,
                data: {
                  ...n.data,
                  ...(patch.name !== undefined ? { label: patch.name } : {}),
                  ...(patch.model !== undefined ? { model: patch.model } : {}),
                },
              }
            : n,
        ),
      )
    }
  }

  const addBlock = useCallback((preset: BlockPreset, position?: { x: number; y: number }) => {
    pushHistory()
    const nid = `agent_${Date.now() % 1000000}`
    const agent: AgentNode = {
      id: nid, name: preset.name, role_prompt: preset.role_prompt, model: '', allowed_folders: [],
    }
    setAgents((prev) => ({ ...prev, [nid]: agent }))
    setNodes((nds) => [
      ...nds,
      {
        id: nid,
        type: 'agent',
        position: position ?? { x: 60, y: 60 + nds.length * 50 },
        data: { label: agent.name, model: '' },
      },
    ])
    setSelected(nid)
  }, [pushHistory, setNodes])

  const onDrop = useCallback((e: DragEvent) => {
    e.preventDefault()
    const raw = e.dataTransfer.getData('application/mars-block')
    if (!raw) return
    const preset: BlockPreset = JSON.parse(raw)
    const position = rfInstance.current?.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    addBlock(preset, position)
  }, [addBlock])

  function deleteAgent() {
    if (!selected) return
    pushHistory()
    setNodes((nds) => nds.filter((n) => n.id !== selected))
    setEdges((eds) => eds.filter((e) => e.source !== selected && e.target !== selected))
    setAgents((prev) => {
      const next = { ...prev }
      delete next[selected]
      return next
    })
    setSelected(null)
  }

  function currentGraph(): Graph {
    return {
      nodes: nodes.map((n) => ({
        ...(agents[n.id] ?? { id: n.id, name: String(n.data.label), role_prompt: '', model: '', allowed_folders: [] }),
        position: n.position,
      })),
      edges: edges.map((e) => ({ source: e.source, target: e.target })),
    }
  }

  function applyGraph(graph: Graph) {
    const positions = layoutPositions(graph)
    const agentMap: Record<string, AgentNode> = {}
    graph.nodes.forEach((n) => (agentMap[n.id] = n))
    setAgents(agentMap)
    setNodes(
      graph.nodes.map((n) => ({
        id: n.id,
        type: 'agent',
        position: n.position ?? positions[n.id],
        data: { label: n.name, model: n.model },
      })),
    )
    setEdges(graph.edges.map((e) => makeEdge(e.source, e.target)))
    setSelected(null)
    setTimeout(() => rfInstance.current?.fitView({ padding: 0.2 }), 50)
  }

  function autoLayout() {
    pushHistory()
    const positions = layoutPositions(currentGraph())
    setNodes((nds) => nds.map((n) => ({ ...n, position: positions[n.id] ?? n.position })))
    setTimeout(() => rfInstance.current?.fitView({ padding: 0.2 }), 50)
  }

  async function save() {
    setError('')
    setMessage('')
    try {
      const updated = await api.put<Service>(`/services/${id}`, {
        name: svcName, description: svcDesc, graph: currentGraph(),
      })
      setService(updated)
      setMessage('저장되었습니다. (DAG 검증 통과)')
      setTimeout(() => setMessage(''), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : '저장 실패')
    }
  }

  async function aiRevise(e: FormEvent) {
    e.preventDefault()
    setError('')
    setMessage('')
    setAiLoading(true)
    try {
      const result = await api.post<{ graph: Graph }>(`/services/${id}/revise`, {
        instruction: aiInstruction,
      })
      pushHistory()
      applyGraph(result.graph)
      setAiInstruction('')
      setMessage('AI 수정안을 적용했습니다. 확인 후 저장을 눌러 주세요. (되돌리기: Cmd+Z)')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 수정 실패')
    } finally {
      setAiLoading(false)
    }
  }

  async function run(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.put<Service>(`/services/${id}`, {
        name: svcName, description: svcDesc, graph: currentGraph(),
      })
      const execution = await api.post<Execution>(`/services/${id}/executions`, { run_prompt: runPrompt })
      navigate(`/executions/${execution.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '실행 실패')
    }
  }

  if (!service) return <div>{error || '불러오는 중...'}</div>

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 10 }}>
        <h1 style={{ margin: 0 }}>{svcName}</h1>
        <div className="row">
          <button className="btn ghost sm" onClick={undo} disabled={undoStack.current.length === 0} title="되돌리기 (Cmd+Z)">
            ↶ 되돌리기
          </button>
          <button className="btn ghost sm" onClick={redo} disabled={redoStack.current.length === 0} title="다시 실행 (Shift+Cmd+Z)">
            ↷ 다시 실행
          </button>
          <button className="btn ghost sm" onClick={autoLayout}>자동 정렬</button>
          <button className="btn" onClick={save}>저장</button>
        </div>
      </div>

      <form className="ai-bar" onSubmit={aiRevise}>
        <span className="ai-bar-label">AI로 수정</span>
        <input
          placeholder='예: "검토 에이전트를 정리 앞에 추가해줘", "분석을 병렬 두 갈래로 나눠줘"'
          value={aiInstruction}
          onChange={(e) => setAiInstruction(e.target.value)}
          required
          minLength={2}
        />
        <button className="btn sm" disabled={aiLoading}>{aiLoading ? '수정 중...' : '적용'}</button>
      </form>

      {message && <div style={{ color: 'var(--success)', fontSize: 13, margin: '8px 0' }}>{message}</div>}
      {error && <div className="error" style={{ margin: '8px 0' }}>{error}</div>}

      <div className="builder3">
        <div className="palette">
          <div className="palette-title">블록</div>
          <div className="palette-hint">드래그하거나 클릭해서 추가</div>
          {BLOCK_PRESETS.map((preset) => {
            const cat = categoryOf(preset.name)
            return (
              <div
                key={preset.name}
                className="palette-block"
                style={{ borderColor: cat.color, background: cat.bg }}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData('application/mars-block', JSON.stringify(preset))
                  e.dataTransfer.effectAllowed = 'move'
                }}
                onClick={() => addBlock(preset)}
              >
                <span className="palette-block-tag" style={{ background: cat.color }}>{cat.tag}</span>
                <div className="palette-block-name">{preset.name}</div>
                <div className="palette-block-hint">{preset.hint}</div>
              </div>
            )
          })}
        </div>

        <div
          className="flow-wrap"
          onDrop={onDrop}
          onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            onInit={(inst: any) => { rfInstance.current = inst }}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, node) => setSelected(node.id)}
            onPaneClick={() => setSelected(null)}
            onBeforeDelete={async () => { pushHistory(); return true }}
            deleteKeyCode={['Backspace', 'Delete']}
            fitView
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>

        <div className="node-panel">
          {selectedAgent ? (
            <>
              <div className="row spread">
                <h2 style={{ margin: 0 }}>블록 설정</h2>
                <button className="btn sm danger" onClick={deleteAgent}>삭제</button>
              </div>
              <label>이름</label>
              <input value={selectedAgent.name} onChange={(e) => updateAgent({ name: e.target.value })} />
              <label>역할 프롬프트</label>
              <textarea
                rows={7}
                value={selectedAgent.role_prompt}
                onChange={(e) => updateAgent({ role_prompt: e.target.value })}
              />
              <label>모델 (비우면 기기 기본값)</label>
              <input
                placeholder="예: gemma3:4b"
                value={selectedAgent.model}
                onChange={(e) => updateAgent({ model: e.target.value })}
              />
              <label>허용 폴더 (쉼표 구분, 비우면 기기 설정 사용)</label>
              <input
                placeholder="/Users/me/Documents"
                value={selectedAgent.allowed_folders.join(', ')}
                onChange={(e) =>
                  updateAgent({
                    allowed_folders: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                  })
                }
              />
              <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 12 }}>
                블록 가장자리의 점을 드래그하면 연결이 만들어지고, 연결선 위 ×를 누르면 삭제됩니다.
              </p>
            </>
          ) : (
            <>
              <h2>서비스 정보</h2>
              <label>이름</label>
              <input value={svcName} onChange={(e) => setSvcName(e.target.value)} />
              <label>설명</label>
              <textarea rows={2} value={svcDesc} onChange={(e) => setSvcDesc(e.target.value)} />

              <h2 style={{ marginTop: 20 }}>서비스 실행</h2>
              <form onSubmit={run}>
                <label>실행 프롬프트</label>
                <textarea
                  rows={4}
                  placeholder="이번 실행에서 처리할 구체적인 요청을 입력하세요"
                  value={runPrompt}
                  onChange={(e) => setRunPrompt(e.target.value)}
                  required
                />
                <button className="btn" style={{ marginTop: 12, width: '100%' }}>실행</button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
