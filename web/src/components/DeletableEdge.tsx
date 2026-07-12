import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@xyflow/react'

export default function DeletableEdge(props: any) {
  const {
    id, sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition, selected, markerEnd, data,
  } = props
  const [path, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition,
  })
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{ strokeWidth: selected ? 2.5 : 1.5, stroke: selected ? '#6366f1' : '#94a3b8' }}
      />
      <EdgeLabelRenderer>
        <button
          className={`edge-del${selected ? ' show' : ''}`}
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          onClick={(e) => {
            e.stopPropagation()
            data?.onDelete?.(id)
          }}
          title="연결 삭제"
        >
          ×
        </button>
      </EdgeLabelRenderer>
    </>
  )
}
