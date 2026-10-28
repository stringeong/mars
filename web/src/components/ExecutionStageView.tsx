import { Edge, Handle, MarkerType, Node, Position, ReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useRef, useState } from 'react'
import { Execution } from '../types'
import { formatClock, taskDuration, taskStatus, taskWorkerLabel } from '../workflow'

const COLUMN_WIDTH = 262
const ROW_HEIGHT = 146
const CARD_WIDTH = 220
const LABEL_OFFSET = 56

function TaskNode({ data }: { data: any }) {
  const status = taskStatus(data.status)
  return <div className={`stage-task ${data.status}`}>
    <Handle type="target" position={Position.Left} isConnectable={false} className="stage-handle" />
    <div className="stage-task-head"><strong title={data.name}>{data.name}</strong>{data.final && <b className="mini-final">FINAL</b>}</div>
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
    const offset = ((tallest - ids.length) * ROW_HEIGHT) / 2
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
  const zoom = width ? Math.min(1, Math.max(fixed ? 0.4 : 0.7, width / contentWidth)) : 1
  const overflow = width > 0 && contentWidth * zoom > width
  return <div ref={wrapRef} className="stage-view" style={{ height: Math.max(220, (tallest * ROW_HEIGHT + LABEL_OFFSET) * zoom + 36) }}>
    <ReactFlow
      key={Math.round(zoom * 100)}
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      defaultViewport={{ x: 16, y: LABEL_OFFSET * zoom + 14, zoom }}
      minZoom={0.5}
      maxZoom={1.5}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      zoomOnScroll={false}
      panOnScroll={!fixed}
      // 고정 모드라도 칸보다 넓으면(좁은 화면) 끌어서 다음 단계를 볼 수 있게 한다
      panOnDrag={!fixed || overflow}
      zoomOnPinch={!fixed}
      zoomOnDoubleClick={!fixed}
      preventScrolling={!fixed}
      proOptions={{ hideAttribution: true }}
    />
    {overflow && <span className="stage-pan-hint">← 가로로 끌거나 스크롤해서 다음 단계를 볼 수 있습니다 →</span>}
  </div>
}
