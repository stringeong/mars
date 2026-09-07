import { X } from 'lucide-react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath, useReactFlow, type EdgeProps } from '@xyflow/react';
import clsx from 'clsx';

export function DeletableEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  selected,
}: EdgeProps) {
  const { setEdges } = useReactFlow();
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setEdges((edges) => edges.filter((edge) => edge.id !== id));
          }}
          title="연결 삭제"
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'all',
          }}
          className={clsx(
            'nodrag nopan flex h-5 w-5 items-center justify-center rounded-full border bg-white text-ink-400 shadow-soft transition hover:scale-110 hover:border-rose-300 hover:text-rose-500',
            selected ? 'opacity-100 border-brand-300 text-brand-500' : 'opacity-60'
          )}
        >
          <X size={11} strokeWidth={2.5} />
        </button>
      </EdgeLabelRenderer>
    </>
  );
}

export const edgeTypes = { default: DeletableEdge };
