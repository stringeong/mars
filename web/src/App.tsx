import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api, getToken } from './api'
import { Device, Service } from './types'
import Sidebar from './components/Sidebar'
import { onServiceRenamed } from './workflow'
import DashboardPage from './pages/DashboardPage'
import DevicesPage from './pages/DevicesPage'
import ExecutionPage from './pages/ExecutionPage'
import FilesPage from './pages/FilesPage'
import HistoryPage from './pages/HistoryPage'
import LoginPage from './pages/LoginPage'
import SettingsPage from './pages/SettingsPage'
import ServiceDetailPage from './pages/ServiceDetailPage'
import ServicesPage from './pages/ServicesPage'
import WorkflowRunPage from './pages/WorkflowRunPage'
import WorkflowSetupPage from './pages/WorkflowSetupPage'

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const location = useLocation()
  const authed = !!getToken()
  // 사이드바의 워크플로우 목록과 워커 온라인 수
  const [services, setServices] = useState<Service[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  useEffect(() => {
    if (!authed) {
      setServices([])
      setDevices([])
      return
    }
    let active = true
    const load = () => {
      api.get<Service[]>('/services').then((items) => { if (active) setServices(items) }).catch(() => {})
      api.get<Device[]>('/devices').then((items) => { if (active) setDevices(items) }).catch(() => {})
    }
    load()
    const timer = window.setInterval(load, 15_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [authed, location.pathname])

  // 어디서 이름을 바꾸든 사이드바 목록에 바로 반영한다
  useEffect(() => onServiceRenamed(({ id, name }) => {
    setServices((current) => current.map((service) => (service.id === id ? { ...service, name } : service)))
  }), [])

  return (
    <div className={authed && location.pathname !== '/login' ? 'layout authenticated-layout' : 'layout'}>
      {authed && location.pathname !== '/login' && (
        <Sidebar services={services} devices={devices} />
      )}
      <main className="content">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<Navigate to="/services" replace />} />
          <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
          <Route path="/services" element={<RequireAuth><ServicesPage /></RequireAuth>} />
          <Route path="/services/:id/run" element={<RequireAuth><WorkflowRunPage /></RequireAuth>} />
          <Route path="/services/:id/setup" element={<RequireAuth><WorkflowSetupPage /></RequireAuth>} />
          <Route path="/services/:id" element={<RequireAuth><ServiceDetailPage /></RequireAuth>} />
          <Route path="/devices" element={<RequireAuth><DevicesPage /></RequireAuth>} />
          <Route path="/files" element={<RequireAuth><FilesPage /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><HistoryPage /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="/executions/:id" element={<RequireAuth><ExecutionPage /></RequireAuth>} />
        </Routes>
      </main>
    </div>
  )
}
