import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api, getToken } from './api'
import { ExecutionListItem } from './types'
import DeviceMonitor from './components/DeviceMonitor'
import Sidebar from './components/Sidebar'
import DashboardPage from './pages/DashboardPage'
import DevicesPage from './pages/DevicesPage'
import ExecutionPage from './pages/ExecutionPage'
import FilesPage from './pages/FilesPage'
import HistoryPage from './pages/HistoryPage'
import LoginPage from './pages/LoginPage'
import MarketplacePage from './pages/MarketplacePage'
import SettingsPage from './pages/SettingsPage'
import ServiceDetailPage from './pages/ServiceDetailPage'
import ServicesPage from './pages/ServicesPage'
import WorkflowRunPage from './pages/WorkflowRunPage'

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const location = useLocation()
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

  return (
    <div className={authed && location.pathname !== '/login' ? 'layout authenticated-layout' : 'layout'}>
      {authed && location.pathname !== '/login' && (
        <Sidebar recentHistory={recentHistory} />
      )}
      <main className="content">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
          <Route path="/services" element={<RequireAuth><ServicesPage /></RequireAuth>} />
          <Route path="/services/:id/run" element={<RequireAuth><WorkflowRunPage /></RequireAuth>} />
          <Route path="/services/:id" element={<RequireAuth><ServiceDetailPage /></RequireAuth>} />
          <Route path="/devices" element={<RequireAuth><DevicesPage /></RequireAuth>} />
          <Route path="/files" element={<RequireAuth><FilesPage /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><HistoryPage /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="/executions/:id" element={<RequireAuth><ExecutionPage /></RequireAuth>} />
        </Routes>
        {authed && location.pathname !== '/login' && <DeviceMonitor />}
      </main>
    </div>
  )
}
