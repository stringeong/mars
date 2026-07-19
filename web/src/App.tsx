import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { getToken, setToken } from './api'
import DevicesPage from './pages/DevicesPage'
import EventsPage from './pages/EventsPage'
import ExecutionPage from './pages/ExecutionPage'
import HistoryPage from './pages/HistoryPage'
import LoginPage from './pages/LoginPage'
import ServiceDetailPage from './pages/ServiceDetailPage'
import ServicesPage from './pages/ServicesPage'
import SettingsPage from './pages/SettingsPage'

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const authed = !!getToken()

  const navItems = [
    { to: '/services', label: '서비스' },
    { to: '/devices', label: '기기 관리' },
    { to: '/history', label: '실행 이력' },
    { to: '/events', label: '활동 로그' },
    { to: '/settings', label: '내 정보' },
  ]

  return (
    <div className="layout">
      {authed && location.pathname !== '/login' && (
        <aside className="sidebar">
          <div className="logo">M.A.R.S</div>
          <nav>
            {navItems.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className={location.pathname.startsWith(item.to) ? 'active' : ''}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <button
            className="btn ghost logout"
            onClick={() => {
              setToken(null)
              navigate('/login')
            }}
          >
            로그아웃
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
          <Route path="/events" element={<RequireAuth><EventsPage /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="/executions/:id" element={<RequireAuth><ExecutionPage /></RequireAuth>} />
        </Routes>
      </main>
    </div>
  )
}
