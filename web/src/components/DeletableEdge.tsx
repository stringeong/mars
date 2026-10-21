import { BaseEdge, EdgeLabelRenderer, EdgeProps, getBezierPath, useReactFlow } from '@xyflow/react'

/** 선택하면 가운데에 삭제(×) 버튼이 나오는 연결선. 키보드 삭제와 같은 경로(deleteElements)로 지운다. */
export default function DeletableEdge(props: EdgeProps) {
  const {
    id, sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition, selected, markerEnd,
  } = props
  const { deleteElements } = useReactFlow()
  const [path, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition,
  })
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        interactionWidth={24}
        style={{ strokeWidth: selected ? 2.5 : 1.5, stroke: selected ? '#6366f1' : '#94a3b8' }}
      />
      {selected && <EdgeLabelRenderer>
        <button
          type="button"
          className="edge-del show nodrag nopan"
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          onClick={(event) => {
            event.stopPropagation()
            deleteElements({ edges: [{ id }] })
          }}
          aria-label="연결 삭제"
          title="연결 삭제 (Delete / Backspace)"
        >
          ×
        </button>
      </EdgeLabelRenderer>}
    </>
  )
}
