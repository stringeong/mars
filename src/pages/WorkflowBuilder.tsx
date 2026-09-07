import { useCallback, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  BackgroundVariant,
  type Connection,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from '@xyflow/react';
import { Play, Save, Share2, History, Maximize2, Pencil } from 'lucide-react';
import { TopBar } from '@/components/layout/TopBar';
import { ComponentPalette, type PaletteItem } from '@/components/workflow/ComponentPalette';
import { NodePropertiesPanel } from '@/components/workflow/NodePropertiesPanel';
import { ResourceStatusBar } from '@/components/workflow/ResourceStatusBar';
import { nodeTypes } from '@/components/workflow/MarsNode';
import { edgeTypes } from '@/components/workflow/DeletableEdge';
import { useData } from '@/context/DataContext';
import type { WorkflowNode, WorkflowNodeData } from '@/types';

let idSeq = 1;
const genId = (prefix: string) => `${prefix}-${Date.now()}-${idSeq++}`;

function WorkflowBuilderInner() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { getWorkflow, saveWorkflow, devices } = useData();
  const workflow = id ? getWorkflow(id) : undefined;

  const [name, setName] = useState(workflow?.name ?? 'Untitled Workflow');
  const [editingName, setEditingName] = useState(false);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<WorkflowNodeData>>((workflow?.nodes as unknown as Node<WorkflowNodeData>[]) ?? []);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>((workflow?.edges as unknown as Edge[]) ?? []);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);
  const [saved, setSaved] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const selectedNode = useMemo(
    () => (nodes.find((n) => n.id === selectedNodeId) as unknown as WorkflowNode | undefined),
    [nodes, selectedNodeId]
  );

  const onConnect = useCallback((connection: Connection) => setEdges((eds) => addEdge({ ...connection, animated: false }, eds)), [setEdges]);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData('application/mars-node');
      if (!raw || !rfInstance || !wrapperRef.current) return;
      const item: PaletteItem = JSON.parse(raw);
      // screenToFlowPosition expects raw viewport (client) coordinates — it
      // resolves the canvas offset internally, unlike the deprecated
      // project() API this replaces.
      const position = rfInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const newNode: Node<WorkflowNodeData> = {
        id: genId('node'),
        type: 'marsNode',
        position,
        data: {
          label: item.label,
          kind: item.kind,
          subtitle: item.subtitle,
          device: devices[0]?.id,
          model: 'Local LLM (Llama 3.1 8B)',
          temperature: 0.7,
          inputVariables: [],
          outputVariables: [],
          status: 'idle',
        },
      };
      setNodes((nds) => nds.concat(newNode));
    },
    [rfInstance, devices, setNodes]
  );

  const onAddNodeFromPalette = useCallback(
    (item: PaletteItem) => {
      const newNode: Node<WorkflowNodeData> = {
        id: genId('node'),
        type: 'marsNode',
        position: { x: 400 + Math.random() * 200, y: 120 + Math.random() * 260 },
        data: {
          label: item.label,
          kind: item.kind,
          subtitle: item.subtitle,
          device: devices[0]?.id,
          model: 'Local LLM (Llama 3.1 8B)',
          temperature: 0.7,
          inputVariables: [],
          outputVariables: [],
          status: 'idle',
        },
      };
      setNodes((nds) => nds.concat(newNode));
    },
    [devices, setNodes]
  );

  const handleNodeChange = (updated: WorkflowNode) => {
    setNodes((nds) => nds.map((n) => (n.id === updated.id ? { ...n, data: updated.data } : n)));
  };

  const handleDeleteNode = () => {
    if (!selectedNodeId) return;
    setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId));
    setEdges((eds) => eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId));
    setSelectedNodeId(null);
  };

  const persist = (status: 'draft' | 'ready') => {
    if (!workflow) return;
    saveWorkflow({
      ...workflow,
      name,
      status,
      nodes: nodes as unknown as WorkflowNode[],
      edges: edges as unknown as Edge[] as any,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  };

  if (!workflow) {
    return (
      <div className="flex flex-1 items-center justify-center text-ink-500">워크플로우를 찾을 수 없습니다.</div>
    );
  }

  return (
    <>
      <TopBar
        title=""
        breadcrumb={['M.A.R.S', 'Workflow Builder']}
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => persist('draft')}
              className="flex items-center gap-1.5 rounded-lg border border-brand-100 bg-white px-3 py-2 text-[12.5px] font-semibold text-ink-700 hover:bg-brand-50"
            >
              <Save size={14} /> {saved ? 'Saved ✓' : 'Save Draft'}
            </button>
            <button
              className="flex items-center gap-1.5 rounded-lg border border-brand-100 bg-white px-3 py-2 text-[12.5px] font-semibold text-ink-700 hover:bg-brand-50"
            >
              <Share2 size={14} /> Share
            </button>
            <button
              onClick={() => {
                persist('ready');
                navigate(`/workflows/${workflow.id}/run`);
              }}
              className="flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-[12.5px] font-bold text-white shadow-soft hover:bg-brand-700"
            >
              <Play size={14} /> Run Workflow
            </button>
          </div>
        }
      />

      {/* Custom title row (edit + live status), placed under TopBar to mirror the Figma canvas header */}
      <div className="flex items-center gap-3 border-b border-brand-100/60 bg-white px-6 py-2.5">
        {editingName ? (
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setEditingName(false)}
            onKeyDown={(e) => e.key === 'Enter' && setEditingName(false)}
            className="rounded-md border border-brand-200 px-2 py-1 text-[14px] font-bold outline-none"
          />
        ) : (
          <button onClick={() => setEditingName(true)} className="flex items-center gap-1.5 text-[14px] font-bold text-ink-900">
            {name} <Pencil size={12} className="text-ink-300" />
          </button>
        )}
        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] font-semibold text-emerald-600">● Live</span>
        <span className="ml-auto flex items-center gap-1.5 text-[11px] text-ink-500">
          <History size={12} /> Last saved just now
        </span>
        <button onClick={() => rfInstance?.fitView({ padding: 0.3 })} className="rounded-md p-1.5 text-ink-500 hover:bg-brand-50">
          <Maximize2 size={14} />
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        <ComponentPalette onAddNode={onAddNodeFromPalette} />

        <div className="relative min-w-0 flex-1" ref={wrapperRef}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setRfInstance}
            onDrop={onDrop}
            onDragOver={(e) => e.preventDefault()}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            deleteKeyCode={['Backspace', 'Delete']}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#dfe2f7" />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              maskColor="rgba(99,102,241,0.06)"
              nodeColor={() => '#c7cafc'}
              className="!border !border-brand-100 !shadow-soft"
            />
          </ReactFlow>
        </div>

        {selectedNode && (
          <NodePropertiesPanel
            node={selectedNode}
            devices={devices}
            onChange={handleNodeChange}
            onClose={() => setSelectedNodeId(null)}
            onDelete={handleDeleteNode}
          />
        )}
      </div>

      <ResourceStatusBar />
    </>
  );
}

export default function WorkflowBuilder() {
  return (
    <ReactFlowProvider>
      <WorkflowBuilderInner />
    </ReactFlowProvider>
  );
}
