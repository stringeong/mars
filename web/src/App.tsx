import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { getToken, setToken } from './api'
import DevicesPage from './pages/DevicesPage'
import ExecutionPage from './pages/ExecutionPage'
import HistoryPage from './pages/HistoryPage'
import LoginPage from './pages/LoginPage'
import ServiceDetailPage from './pages/ServiceDetailPage'
import ServicesPage from './pages/ServicesPage'

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const authed = !!getToken()
  const navItems = [
    { to: '/services', label: 'Workflows', icon: 'W' },
    { to: '/devices', label: 'Workers', icon: 'R' },
    { to: '/history', label: 'Run history', icon: 'H' },
  ]

  return (
    <div className="layout">
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
          <Route path="/services/:id" element={<RequireAuth><ServiceDetailPage /></RequireAuth>} />
          <Route path="/devices" element={<RequireAuth><DevicesPage /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><HistoryPage /></RequireAuth>} />
          <Route path="/executions/:id" element={<RequireAuth><ExecutionPage /></RequireAuth>} />
        </Routes>
      </main>
    </div>
  )
}
