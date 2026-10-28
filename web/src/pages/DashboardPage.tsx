import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Device, ExecutionListItem, Service, WorkflowFolder } from '../types'

// 폴더 칩에서 고른 범위. all: 전체, none: 미분류, 숫자: 그 폴더
type FolderFilter = 'all' | 'none' | number

export default function DashboardPage() {
  const [services, setServices] = useState<Service[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [executions, setExecutions] = useState<ExecutionListItem[]>([])
  const [query, setQuery] = useState('')
  const [folders, setFolders] = useState<WorkflowFolder[]>([])
  const [folderFilter, setFolderFilter] = useState<FolderFilter>('all')
  const [dropTarget, setDropTarget] = useState<FolderFilter | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.allSettled([
      api.get<Service[]>('/services').then(setServices),
      api.get<Device[]>('/devices').then(setDevices),
      api.get<ExecutionListItem[]>('/executions').then(setExecutions),
      api.get<WorkflowFolder[]>('/folders').then(setFolders),
    ])
  }, [])

  function countIn(filter: FolderFilter) {
    return filter === 'all' ? services.length : services.filter((service) => (service.folder_id ?? 'none') === filter).length
  }
  async function createFolder() {
    const name = prompt('새 폴더 이름')?.trim()
    if (!name) return
    try {
      const folder = await api.post<WorkflowFolder>('/folders', { name })
      setFolders((current) => [...current, folder].sort((a, b) => a.name.localeCompare(b.name)))
      setFolderFilter(folder.id)
    } catch (cause) { alert(cause instanceof Error ? cause.message : '폴더를 만들지 못했습니다.') }
  }
  async function renameFolder(folder: WorkflowFolder) {
    const name = prompt('폴더 이름 바꾸기', folder.name)?.trim()
    if (!name || name === folder.name) return
    try {
      const renamed = await api.put<WorkflowFolder>(`/folders/${folder.id}`, { name })
      setFolders((current) => current.map((item) => (item.id === renamed.id ? renamed : item)))
    } catch (cause) { alert(cause instanceof Error ? cause.message : '폴더 이름을 바꾸지 못했습니다.') }
  }
  async function removeFolder(folder: WorkflowFolder) {
    if (!confirm(`'${folder.name}' 폴더를 지울까요? 안에 있던 워크플로우는 지워지지 않고 미분류로 옮겨집니다.`)) return
    try {
      await api.delete(`/folders/${folder.id}`)
      setFolders((current) => current.filter((item) => item.id !== folder.id))
      setServices((current) => current.map((service) => (service.folder_id === folder.id ? { ...service, folder_id: null } : service)))
      setFolderFilter('all')
    } catch (cause) { alert(cause instanceof Error ? cause.message : '폴더를 지우지 못했습니다.') }
  }
  async function moveTo(serviceId: number, folderId: number | null) {
    try {
      const moved = await api.put<Service>(`/services/${serviceId}/folder`, { folder_id: folderId })
      setServices((current) => current.map((service) => (service.id === moved.id ? { ...service, folder_id: moved.folder_id } : service)))
    } catch (cause) { alert(cause instanceof Error ? cause.message : '폴더로 옮기지 못했습니다.') }
  }
  // 카드를 폴더 칩에 끌어다 놓아도 옮겨진다
  function dropProps(filter: FolderFilter) {
    if (filter === 'all') return {}
    return {
      onDragOver: (event: React.DragEvent) => { if (event.dataTransfer.types.includes('text/mars-service')) { event.preventDefault(); setDropTarget(filter) } },
      onDragLeave: () => setDropTarget(null),
      onDrop: (event: React.DragEvent) => {
        event.preventDefault(); setDropTarget(null)
        const id = Number(event.dataTransfer.getData('text/mars-service'))
        if (id) moveTo(id, filter === 'none' ? null : filter)
      },
    }
  }

  const filtered = useMemo(() => services.filter((service) =>
    (folderFilter === 'all' || (service.folder_id ?? 'none') === folderFilter)
    && `${service.name} ${service.description}`.toLowerCase().includes(query.toLowerCase()),
  ), [services, query, folderFilter])
  const currentFolder = typeof folderFilter === 'number' ? folders.find((folder) => folder.id === folderFilter) : undefined
  const online = devices.filter((device) => device.online).length
  const running = executions.filter((execution) => execution.status === 'running').length

  return <div className="overview-page">
    <header className="page-heading"><div><div className="breadcrumb">M.A.R.S <span>/</span> Dashboard</div><h1>Dashboard</h1><p>Your workflows, workers, and recent activity at a glance.</p></div><button className="generate-button" onClick={() => navigate('/services')}>+ New workflow</button></header>
    <section className="stat-grid">
      <div className="stat-card"><span>Total workflows</span><strong>{services.length}</strong><small>saved services</small></div>
      <div className="stat-card"><span>Online workers</span><strong>{online}/{devices.length}</strong><small>available devices</small></div>
      <div className="stat-card"><span>Running now</span><strong className={running ? 'accent' : ''}>{running}</strong><small>active executions</small></div>
      <div className="stat-card"><span>Recent runs</span><strong>{executions.length}</strong><small>execution records</small></div>
    </section>
    <section className="dashboard-workflows">
      <div className="section-heading dashboard-section-heading"><div><span className="eyebrow">YOUR WORKSPACE</span><h2>My workflows</h2></div><input className="compact-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search workflows" /></div>
      <div className="folder-bar">
        {(['all', 'none'] as const).map((filter) => <button type="button" key={filter} className={`folder-chip${folderFilter === filter ? ' active' : ''}${dropTarget === filter ? ' drop' : ''}`} onClick={() => setFolderFilter(filter)} {...dropProps(filter)}>{filter === 'all' ? '전체' : '미분류'} <span>{countIn(filter)}</span></button>)}
        {folders.map((folder) => <button type="button" key={folder.id} className={`folder-chip${folderFilter === folder.id ? ' active' : ''}${dropTarget === folder.id ? ' drop' : ''}`} onClick={() => setFolderFilter(folder.id)} {...dropProps(folder.id)}>📁 {folder.name} <span>{countIn(folder.id)}</span></button>)}
        <button type="button" className="folder-chip folder-add" onClick={createFolder}>+ 새 폴더</button>
        {currentFolder && <span className="folder-actions"><button type="button" onClick={() => renameFolder(currentFolder)}>이름 바꾸기</button><button type="button" className="danger" onClick={() => removeFolder(currentFolder)}>폴더 삭제</button></span>}
      </div>
      {folders.length > 0 && <p className="folder-hint">카드를 폴더로 끌어다 놓거나, 카드 아래에서 폴더를 골라 옮길 수 있어요.</p>}
      <div className="dashboard-workflow-grid">
        {folderFilter === 'all' && <button className="new-workflow-card" onClick={() => navigate('/services')}><b>+</b><strong>Create a new workflow</strong><small>Build an editable multi-agent workflow</small></button>}
        {filtered.map((service) => <div className="dashboard-workflow-card" key={service.id} draggable onDragStart={(event) => { event.dataTransfer.setData('text/mars-service', String(service.id)); event.dataTransfer.effectAllowed = 'move' }}>
          <button type="button" className="card-open" onClick={() => navigate(`/services/${service.id}`)}><span className="workflow-avatar">{service.name.slice(0, 1).toUpperCase()}</span><strong>{service.name}</strong><p>{service.description || 'No description provided.'}</p><small>{service.graph.nodes.length} blocks · Updated {new Date(service.updated_at).toLocaleDateString()}</small></button>
          {folders.length > 0 && <select className="card-folder" aria-label={`${service.name} 폴더`} value={service.folder_id ?? ''} onChange={(event) => moveTo(service.id, event.target.value ? Number(event.target.value) : null)}>
            <option value="">미분류</option>
            {folders.map((folder) => <option key={folder.id} value={folder.id}>📁 {folder.name}</option>)}
          </select>}
        </div>)}
      </div>
      {!filtered.length && services.length > 0 && <div className="empty-workflows">{query ? 'No workflows match your search.' : '이 폴더에는 아직 워크플로우가 없어요. 카드를 끌어다 놓아 보세요.'}</div>}
    </section>
  </div>
}
