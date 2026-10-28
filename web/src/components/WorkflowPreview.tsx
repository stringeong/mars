import { Background, Edge, MarkerType, Node, ReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { blockId, Demo } from '../demos'
import { stagePositions } from '../flowLayout'
import AgentBlockNode from './AgentBlockNode'
import DeletableEdge from './DeletableEdge'

const nodeTypes = { agent: AgentBlockNode }
const edgeTypes = { deletable: DeletableEdge }
const CLOUD_NAMES = { openai: 'OpenAI', anthropic: 'Anthropic', gemini: 'Gemini' }

/** 제품 소개의 예시 캔버스. 편집기와 같은 블록·연결선·배치 규칙으로 그린다.
 *  블록을 끌 수는 없고, onSelect가 있으면 눌러서 고를 블록을 정한다(편집 예시). */
export default function WorkflowPreview({ demo, model, selectedId, onSelect }: { demo: Demo; model: string; selectedId?: string | null; onSelect?: (id: string) => void }) {
  const columns = demo.stages.map((stage, column) => stage.map((_, row) => blockId(column, row)))
  const positions = stagePositions(columns)
  const nodes: Node[] = demo.stages.flatMap((stage, column) => stage.map((block, row) => {
    const id = blockId(column, row)
    const cloud = block.cloud ? `클라우드 · ${CLOUD_NAMES[block.cloud.provider]}` : ''
    return {
      id,
      type: 'agent',
      position: positions[id],
      selected: id === selectedId,
      data: {
        label: block.name,
        model: block.cloud ? block.cloud.model : block.model ?? model,
        final: block.final,
        workerName: cloud || (block.autoWorker ? '자동 배정' : block.device),
        directories: block.input?.startsWith('디렉터리') ? [block.input.replace(/^디렉터리 · /, '')] : [],
        files: block.files ?? (block.input && !block.input.startsWith('디렉터리') ? [block.input] : []),
      },
    }
  }))
  const edges: Edge[] = columns.slice(1).flatMap((targets, index) => columns[index].flatMap((source) => targets.map((target) => ({
    id: `${source}-${target}`, source, target, type: 'deletable', markerEnd: { type: MarkerType.ArrowClosed },
  }))))

  // 좁은 화면에서도 글씨가 읽히도록 단계 수만큼 최소 폭을 두고, 넘치면 가로로 스크롤한다
  // 병렬 블록이 많아 열이 높아지면 캔버스도 키워 블록이 너무 작아지지 않게 한다
  const tallest = Math.max(...demo.stages.map((stage) => stage.length))
  return <div className="mk-flow-scroll"><div className={`mk-flow-preview${onSelect ? ' editable' : ''}`} style={{ minWidth: demo.stages.length * 210, height: Math.max(300, 100 + tallest * 120) }}>
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={onSelect ? (_, node) => onSelect(node.id) : undefined}
      fitView
      fitViewOptions={{ padding: 0.08 }}
      minZoom={0.3}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable={false}
      zoomOnScroll={false}
      zoomOnPinch={false}
      zoomOnDoubleClick={false}
      panOnDrag={false}
      preventScrolling={false}
      proOptions={{ hideAttribution: true }}
    ><Background /></ReactFlow>
  </div></div>
}
