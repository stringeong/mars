import { Link, useLocation, useNavigate } from 'react-router-dom'
import { setToken } from '../api'
import { ExecutionListItem } from '../types'
import AppIcon from './AppIcon'

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: 'dashboard' as const },
  { to: '/services', label: 'Workflows', icon: 'workflow' as const },
  { to: '/devices', label: 'Workers', icon: 'workers' as const },
  { to: '/files', label: 'Files', icon: 'files' as const },
  { to: '/history', label: 'Run history', icon: 'history' as const },
  { to: '/marketplace', label: 'Marketplace', icon: 'marketplace' as const },
]

export default function Sidebar({ recentHistory }: { recentHistory: ExecutionListItem[] }) {
  const location = useLocation()
  const navigate = useNavigate()
  const workflowMatch = location.pathname.match(/^\/services\/(\d+)(?:\/(run))?$/)
  const workflowId = workflowMatch?.[1]
  const workflowStage = location.pathname === '/services' ? 0 : workflowMatch?.[2] === 'run' ? 2 : workflowId ? 1 : 0
  const workflowSteps = [
    { label: 'Create workflow', to: '/services' },
    { label: 'Build & configure', to: workflowId ? `/services/${workflowId}` : undefined },
    { label: 'Run workflow', to: workflowId ? `/services/${workflowId}/run` : undefined },
  ]

  return <aside className="sidebar">
    <Link to="/dashboard" className="brand"><span className="brand-mark">M</span><span className="brand-copy"><strong>M.A.R.S</strong><small>Multi-Agent Resource Sharing</small></span></Link>
    <div className="workspace-label">WORKSPACE</div>
    <nav>{navItems.map((item) => <div className="nav-group" key={item.to}>
      <Link to={item.to} className={location.pathname.startsWith(item.to) ? 'active' : ''}><span className="nav-icon"><AppIcon name={item.icon} /></span><span className="nav-label">{item.label}</span></Link>
      {item.to === '/services' && location.pathname.startsWith('/services') && <div className="workflow-subnav" aria-label="Workflow progress">
        {workflowSteps.map((step, index) => step.to
          ? <Link key={step.label} to={step.to} className={`${index === workflowStage ? 'current' : ''} ${index < workflowStage ? 'complete' : ''}`}><i>{index < workflowStage ? '✓' : index + 1}</i><span>{step.label}</span></Link>
          : <span key={step.label} className="disabled"><i>{index + 1}</i><span>{step.label}</span></span>)}
      </div>}
    </div>)}</nav>
    <section className="sidebar-history">
      <div className="sidebar-history-heading"><span>RECENT RUNS</span><Link to="/history">View all</Link></div>
      <div className="sidebar-history-list">
        {recentHistory.map((item) => <Link key={item.id} to={'/executions/' + item.id} className={location.pathname === '/executions/' + item.id ? 'current' : ''}><span className={'sidebar-run-dot ' + item.status} /><span><strong>{item.service_name || 'Run #' + item.id}</strong><small>{item.status} · #{item.id}</small></span></Link>)}
        {!recentHistory.length && <small className="sidebar-history-empty">No execution history yet.</small>}
      </div>
    </section>
    <div className="sidebar-status"><span className="status-dot" /> System connected</div>
    <button className="btn ghost logout" onClick={() => { setToken(null); navigate('/login') }}>Sign out</button>
  </aside>
}
