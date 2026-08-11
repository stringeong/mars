import { useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, getToken, setToken } from './api'
import { ExecutionListItem } from './types'
import DeviceMonitor from './components/DeviceMonitor'
import DevicesPage from './pages/DevicesPage'
import ExecutionPage from './pages/ExecutionPage'
import FilesPage from './pages/FilesPage'
import HistoryPage from './pages/HistoryPage'
import LoginPage from './pages/LoginPage'
import ServiceDetailPage from './pages/ServiceDetailPage'
import ServicesPage from './pages/ServicesPage'
import WorkflowRunPage from './pages/WorkflowRunPage'

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const authed = !!getToken()
  const [recentHistory, setRecentHistory] = useState<ExecutionListItem[]>([])
  useEffect(() => {
    if (!authed) {
      setRecentHistory([])
      return
    }
    let active = true
    const loadHistory = () => api.get<ExecutionListItem[]>("/executions")
      .then((items) => { if (active) setRecentHistory(items.slice(0, 20)) })
      .catch(() => {})
    loadHistory()
    const timer = window.setInterval(loadHistory, 10_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [authed, location.pathname])

  const navItems = [
    { to: '/services', label: 'Workflows', icon: 'W' },
    { to: '/devices', label: 'Workers', icon: 'R' },
    { to: '/files', label: 'Files', icon: 'F' },
    { to: '/history', label: 'Run history', icon: 'H' },
  ]

  return (
    <div className={authed && location.pathname !== '/login' ? 'layout authenticated-layout' : 'layout'}>
      {authed && location.pathname !== '/login' && (
        <aside className="sidebar">
          <Link to="/services" className="brand">
            <span className="brand-mark">M</span><span>M.A.R.S</span>
          </Link>
          <div className="workspace-label">ORCHESTRATION</div>
          <nav>
            {navItems.map((item) => (
              <Link key={item.to} to={item.to} className={location.pathname.startsWith(item.to) ? 'active' : ''}>
                <span className="nav-icon">{item.icon}</span>{item.label}
              </Link>
            ))}
          </nav>
          <section className="sidebar-history">
            <div className="sidebar-history-heading"><span>RECENT RUNS</span><Link to="/history">View all</Link></div>
            <div className="sidebar-history-list">
              {recentHistory.map((item) => (
                <Link key={item.id} to={'/executions/' + item.id} className={location.pathname === '/executions/' + item.id ? 'current' : ''}>
                  <span className={'sidebar-run-dot ' + item.status} />
                  <span><strong>{item.service_name || 'Run #' + item.id}</strong><small>{item.status} · #{item.id}</small></span>
                </Link>
              ))}
              {!recentHistory.length && <small className="sidebar-history-empty">No execution history yet.</small>}
            </div>
          </section>
          <div className="sidebar-status"><span className="status-dot" /> System connected</div>
          <button className="btn ghost logout" onClick={() => { setToken(null); navigate('/login') }}>
            Sign out
          </button>
        </aside>
      )}
      <main className="content">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<Navigate to="/services" replace />} />
          <Route path="/services" element={<RequireAuth><ServicesPage /></RequireAuth>} />
          <Route path="/services/:id/run" element={<RequireAuth><WorkflowRunPage /></RequireAuth>} />
          <Route path="/services/:id" element={<RequireAuth><ServiceDetailPage /></RequireAuth>} />
          <Route path="/devices" element={<RequireAuth><DevicesPage /></RequireAuth>} />
          <Route path="/files" element={<RequireAuth><FilesPage /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><HistoryPage /></RequireAuth>} />
          <Route path="/executions/:id" element={<RequireAuth><ExecutionPage /></RequireAuth>} />
        </Routes>
        {authed && location.pathname !== '/login' && <DeviceMonitor />}
      </main>
    </div>
  )
}
