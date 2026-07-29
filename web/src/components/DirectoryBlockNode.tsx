import { Handle, Position } from '@xyflow/react'

export default function DirectoryBlockNode({
  data,
  selected,
}: {
  data: {
    label: string
    deviceName?: string
    permission?: string
  }
  selected?: boolean
}) {
  return (
    <div className={`directory-block${selected ? ' selected' : ''}`}>
      <div className="directory-block-tag">Directory</div>
      <div className="directory-block-name">{data.label}</div>

      {data.deviceName && (
        <div className="directory-block-device">
          {data.deviceName}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Right}
        id="directory-output"
        className="block-handle directory-handle"
      />
    </div>
  )
}