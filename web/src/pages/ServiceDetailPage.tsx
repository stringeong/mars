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
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { AgentNode, Execution, Graph, Service } from '../types'

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
    pos[n.id] = { x: lv * 260 + 40, y: (counts[lv] - 1) * 120 + 40 }
  })
  return pos
}

export default function ServiceDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [service, setService] = useState<Service | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [agents, setAgents] = useState<Record<string, AgentNode>>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [runPrompt, setRunPrompt] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<Service>(`/services/${id}`).then((s) => {
      setService(s)
      const positions = layoutPositions(s.graph)
      const agentMap: Record<string, AgentNode> = {}
      s.graph.nodes.forEach((n) => (agentMap[n.id] = n))
      setAgents(agentMap)
      setNodes(
        s.graph.nodes.map((n) => ({
          id: n.id,
          position: n.position ?? positions[n.id],
          data: { label: n.name },
          style: nodeStyle,
        })),
      )
      setEdges(
        s.graph.edges.map((e) => ({
          id: `${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          markerEnd: { type: MarkerType.ArrowClosed },
          animated: true,
        })),
      )
    }).catch((e) => setError(e.message))
  }, [id])

  const onConnect = useCallback(
    (conn: Connection) =>
      setEdges((eds) =>
        addEdge({ ...conn, markerEnd: { type: MarkerType.ArrowClosed }, animated: true }, eds),
      ),
    [setEdges],
  )

  const selectedAgent = selected ? agents[selected] : null

  function updateAgent(patch: Partial<AgentNode>) {
    if (!selected) return
    setAgents((prev) => ({ ...prev, [selected]: { ...prev[selected], ...patch } }))
    if (patch.name !== undefined) {
      setNodes((nds) =>
        nds.map((n) => (n.id === selected ? { ...n, data: { label: patch.name! } } : n)),
      )
    }
  }

  function addAgent() {
    const nid = `agent_${Date.now() % 100000}`
    const agent: AgentNode = { id: nid, name: '새 에이전트', role_prompt: '', model: '', allowed_folders: [] }
    setAgents((prev) => ({ ...prev, [nid]: agent }))
    setNodes((nds) => [
      ...nds,
      { id: nid, position: { x: 60, y: 60 + nds.length * 40 }, data: { label: agent.name }, style: nodeStyle },
    ])
    setSelected(nid)
  }

  function deleteAgent() {
    if (!selected) return
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

  async function save() {
    setError('')
    setMessage('')
    try {
      const updated = await api.put<Service>(`/services/${id}`, { graph: currentGraph() })
      setService(updated)
      setMessage('저장되었습니다. (DAG 검증 통과)')
    } catch (e) {
      setError(e instanceof Error ? e.message : '저장 실패')  // UC-202 e301
    }
  }

  async function run(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      await api.put<Service>(`/services/${id}`, { graph: currentGraph() })
      const execution = await api.post<Execution>(`/services/${id}/executions`, { run_prompt: runPrompt })
      navigate(`/executions/${execution.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '실행 실패')
    }
  }

  if (!service) return <div>{error || '불러오는 중...'}</div>

  return (
    <div>
      <div className="row spread">
        <div>
          <h1>{service.name}</h1>
          <p className="subtitle">{service.description}</p>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={addAgent}>+ 에이전트 추가</button>
          <button className="btn" onClick={save}>저장</button>
        </div>
      </div>
      {message && <div style={{ color: 'var(--success)', fontSize: 13, marginBottom: 8 }}>{message}</div>}
      {error && <div className="error" style={{ marginBottom: 8 }}>{error}</div>}

      <div className="builder-grid">
        <div className="flow-wrap">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, node) => setSelected(node.id)}
            onPaneClick={() => setSelected(null)}
            fitView
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>

        <div className="node-panel">
          {selectedAgent ? (
            <>
              <h2>에이전트 설정</h2>
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
                placeholder="예: qwen3:4b"
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
              <div style={{ marginTop: 16 }}>
                <button className="btn sm danger" onClick={deleteAgent}>이 에이전트 삭제</button>
              </div>
            </>
          ) : (
            <>
              <h2>서비스 실행</h2>
              <p style={{ fontSize: 13, color: 'var(--muted)', margin: '8px 0' }}>
                노드를 클릭하면 에이전트를 편집할 수 있습니다. 노드의 가장자리를 드래그해 연결을 만드세요.
              </p>
              <form onSubmit={run}>
                <label>실행 프롬프트</label>
                <textarea
                  rows={5}
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

const nodeStyle = {
  background: '#eef2ff',
  border: '2px solid #6366f1',
  borderRadius: 10,
  padding: 10,
  fontSize: 13,
  fontWeight: 600,
}
