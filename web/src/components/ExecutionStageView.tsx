import { Edge, Handle, MarkerType, Node, Position, ReactFlow, ReactFlowInstance } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useRef, useState } from 'react'
import { Execution } from '../types'
import { formatClock, taskDuration, taskStatus, taskWorkerLabel } from '../workflow'

const COLUMN_WIDTH = 262
// 카드 높이(약 101px) + 간격 12px
const ROW_HEIGHT = 113
const CARD_WIDTH = 220
const LABEL_OFFSET = 56

function TaskNode({ data }: { data: any }) {
  const status = taskStatus(data.status)
  return <div className={`stage-task ${data.status}`}>
    <Handle type="target" position={Position.Left} isConnectable={false} className="stage-handle" />
    <div className="stage-task-head"><strong title={data.name}>{data.name}</strong>{data.notice && <b className="mini-notice" title={data.notice} aria-label="입력 일부가 빠진 채 실행됨">!</b>}{data.final && <b className="mini-final">FINAL</b>}</div>
    <span className={`task-status ${data.status}`}><i aria-hidden="true">{status.icon}</i>{status.label}</span>
    <dl>
      <div><dt>워커</dt><dd title={data.worker}>{data.worker}</dd></div>
      <div><dt>시작</dt><dd>{data.start}</dd></div>
      <div><dt>종료</dt><dd>{data.end}</dd></div>
      <div><dt>소요</dt><dd>{data.duration}</dd></div>
    </dl>
    <Handle type="source" position={Position.Right} isConnectable={false} className="stage-handle" />
  </div>
}

function StageLabelNode({ data }: { data: any }) {
  return <div className="stage-label"><strong>{data.label}</strong><span>{data.count}개 블록</span></div>
}

const nodeTypes = { task: TaskNode, stageLabel: StageLabelNode }

/** DAG 깊이별 단계를 열로 배치하고 의존 관계를 선으로 그린다. 같은 열은 동시에 실행될 수 있다. */
/** fixed: 제품 소개 미리보기처럼 끌기·스크롤·확대를 막고, 모든 단계가 칸 안에 들어오게 줄여 보여준다 */
export default function ExecutionStageView({ execution, finalNodeIds, now, fixed = false }: { execution: Execution; finalNodeIds: Set<string>; now: number; fixed?: boolean }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const element = wrapRef.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const taskByNode = new Map(execution.tasks.map((task) => [task.node_id, task]))
  // 이전 실행처럼 단계 정보가 없으면 한 열로 보여준다
  const stages = execution.stages?.length ? execution.stages : [execution.tasks.map((task) => task.node_id)]
  const tallest = Math.max(1, ...stages.map((ids) => ids.length))

  const nodes: Node[] = stages.flatMap((ids, column) => {
    // 블록이 적은 단계도 위에서부터 놓아, 스크롤하지 않아도 모든 단계의 첫 블록이 보이게 한다
    const offset = 0
    const label: Node = {
      id: `stage-${column}`,
      type: 'stageLabel',
      position: { x: column * COLUMN_WIDTH, y: -LABEL_OFFSET },
      data: { label: `${column + 1}단계`, count: ids.length },
      selectable: false,
    }
    const tasks: Node[] = ids.flatMap((nodeId, row) => {
      const task = taskByNode.get(nodeId)
      if (!task) return []
      return [{
        id: nodeId,
        type: 'task',
        position: { x: column * COLUMN_WIDTH, y: offset + row * ROW_HEIGHT },
        data: {
          name: task.agent_name,
          status: task.status,
          notice: task.notice,
          final: finalNodeIds.has(nodeId),
          worker: taskWorkerLabel(task),
          start: formatClock(task.started_at),
          end: formatClock(task.finished_at),
          duration: taskDuration(task, now),
        },
      }]
    })
    return [label, ...tasks]
  })

  const edges: Edge[] = (execution.edges ?? []).map((edge) => {
    const source = taskByNode.get(edge.source)
    const target = taskByNode.get(edge.target)
    return {
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      markerEnd: { type: MarkerType.ArrowClosed },
      animated: target?.status === 'running',
      className: source?.status === 'done' ? 'stage-edge done' : 'stage-edge',
    }
  })

  // 칸 너비에 맞춰 줄이되 글씨가 읽히지 않을 만큼(0.7배 미만) 줄이지 않고, 1단계부터 왼쪽 정렬한다.
  // 넘치는 단계는 가로로 끌거나 스크롤해서 본다.
  const contentWidth = (stages.length - 1) * COLUMN_WIDTH + CARD_WIDTH + 32
  const drawnWidth = contentWidth - 32
  const zoom = width ? Math.min(1, Math.max(fixed ? 0.4 : 0.7, width / contentWidth)) : 1
  const overflow = width > 0 && contentWidth * zoom > width
  const height = Math.max(220, (tallest * ROW_HEIGHT + LABEL_OFFSET) * zoom + 36)
  // 다 들어가면 가운데에, 넘치면 1단계부터 왼쪽에 놓는다
  const startX = overflow || !width ? 16 : Math.max(16, (width - drawnWidth * zoom) / 2)
  // 넘칠 때 가로로 움직일 수 있는 범위 (화면 기준 x): 마지막 단계 오른쪽 끝이 16px 여백을 두고 보일 때까지
  const minX = Math.min(16, width - drawnWidth * zoom - 16)
  const clampX = (x: number) => Math.min(16, Math.max(minX, x))
  // 위아래로는 움직이지 않게 막는다. 마우스 휠은 페이지 스크롤에 쓴다.
  const top = -(LABEL_OFFSET * zoom + 14) / zoom
  const extent: [[number, number], [number, number]] = [[-16 / zoom, top], [drawnWidth + 16 / zoom, top + height / zoom]]
  const [flow, setFlow] = useState<ReactFlowInstance | null>(null)
  const [viewX, setViewX] = useState(startX)
  // 칸 너비·단계 수가 바뀔 때마다 실제 칸 너비로 다시 맞춘다 (가운데 정렬 / 넘치면 1단계부터)
  useEffect(() => {
    const element = wrapRef.current
    if (!flow || !element) return
    const box = element.clientWidth
    const x = contentWidth * zoom > box ? 16 : Math.max(16, (box - drawnWidth * zoom) / 2)
    setViewX(x)
    void flow.setViewport({ x, y: LABEL_OFFSET * zoom + 14, zoom })
  }, [flow, width, zoom, contentWidth, drawnWidth])
  const step = (direction: 1 | -1) => {
    if (!flow) return
    const viewport = flow.getViewport()
    const x = clampX(viewport.x - direction * COLUMN_WIDTH * zoom)
    setViewX(x)
    void flow.setViewport({ ...viewport, x }, { duration: 250 })
  }
  return <div ref={wrapRef} className="stage-view" style={{ height }}>
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      defaultViewport={{ x: startX, y: LABEL_OFFSET * zoom + 14, zoom }}
      onInit={setFlow}
      onMove={(_, viewport) => setViewX(viewport.x)}
      minZoom={0.3}
      maxZoom={1.5}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      // 범위가 칸보다 좁으면 React Flow가 내용을 가운데로 옮겨 버리므로, 넘칠 때(끌기가 켜질 때)만 범위를 건다
      translateExtent={overflow ? extent : undefined}
      zoomOnScroll={false}
      panOnScroll={false}
      // 칸보다 넓을 때만 가로로 끌거나 양옆 화살표로 다음 단계를 볼 수 있게 한다
      panOnDrag={overflow}
      zoomOnPinch={false}
      zoomOnDoubleClick={false}
      preventScrolling={false}
      proOptions={{ hideAttribution: true }}
    />
    {overflow && <>
      <button type="button" className="stage-nav prev" aria-label="이전 단계 보기" disabled={viewX >= 15.5} onClick={() => step(-1)}>‹</button>
      <button type="button" className="stage-nav next" aria-label="다음 단계 보기" disabled={viewX <= minX + 0.5} onClick={() => step(1)}>›</button>
      <span className="stage-pan-hint">← 끌거나 양옆 화살표로 다른 단계를 볼 수 있어요 →</span>
    </>}
  </div>
}
