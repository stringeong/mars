export default function AgentBlockNode({
  data,
  selected,
}: {
  data: any
  selected?: boolean
}) {
  const category = categoryOf(
    String(data.label ?? ''),
  )

  return (
    <div
      className={
        `agent-block${selected ? ' selected' : ''}`
      }
      style={{
        borderColor: category.color,
        background: category.bg,
      }}
    >
      <div
        className="agent-block-tag"
        style={{
          background: category.color,
        }}
      >
        {category.tag}
      </div>

      <div className="agent-block-name">
        {data.label}
      </div>

      {data.model ? (
        <div className="agent-block-model">
          {data.model}
        </div>
      ) : null}

      <Handle
        type="target"
        position={Position.Left}
        id="workflow-input"
        className={
          'block-handle workflow-input-handle'
        }
      />

      <Handle
        type="target"
        position={Position.Left}
        id="directory-input"
        className={
          'block-handle directory-input-handle'
        }
      />

      <Handle
        type="source"
        position={Position.Right}
        id="workflow-output"
        className={
          'block-handle workflow-output-handle'
        }
      />
    </div>
  )
}