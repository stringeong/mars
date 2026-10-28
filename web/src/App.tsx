import { CSSProperties, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api, getToken } from './api'
import { Device, Service } from './types'
import Sidebar, { loadSidebarLayout, saveSidebarLayout, SIDEBAR_COLLAPSED_WIDTH, SidebarLayout } from './components/Sidebar'
import { onServiceDeleted, onServiceRenamed } from './workflow'
import DashboardPage from './pages/DashboardPage'
import DevicesPage from './pages/DevicesPage'
import DownloadPage from './pages/DownloadPage'
import ExamplesPage from './pages/ExamplesPage'
import ExecutionPage from './pages/ExecutionPage'
import FilesPage from './pages/FilesPage'
import HistoryPage from './pages/HistoryPage'
import LoginPage from './pages/LoginPage'
import ProductPage from './pages/ProductPage'
import SettingsPage from './pages/SettingsPage'
import ServiceDetailPage from './pages/ServiceDetailPage'
import ServicesPage from './pages/ServicesPage'
import WorkflowRunPage from './pages/WorkflowRunPage'
import WorkflowSetupPage from './pages/WorkflowSetupPage'

// 로그인 없이 보는 화면: 사이드바 없이 전체 폭을 쓴다
const PUBLIC_PATHS = ['/login', '/about', '/examples', '/download']

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const location = useLocation()
  const authed = !!getToken()
  const withShell = authed && !PUBLIC_PATHS.includes(location.pathname)
  // 사이드바 폭·접힘 상태 (브라우저에 기억한다)
  const [sidebarLayout, setSidebarLayout] = useState<SidebarLayout>(loadSidebarLayout)
  function changeSidebarLayout(next: SidebarLayout) {
    setSidebarLayout(next)
    saveSidebarLayout(next)
  }
  const shellStyle = { '--sidebar-width': `${sidebarLayout.collapsed ? SIDEBAR_COLLAPSED_WIDTH : sidebarLayout.width}px` } as CSSProperties

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
  useEffect(() => onServiceDeleted((id) => {
    setServices((current) => current.filter((service) => service.id !== id))
  }), [])

  useEffect(() => onServiceRenamed(({ id, name }) => {
    setServices((current) => current.map((service) => (service.id === id ? { ...service, name } : service)))
  }), [])

  return (
    <div className={withShell ? 'layout authenticated-layout' : 'layout'} style={withShell ? shellStyle : undefined}>
      {withShell && (
        <Sidebar services={services} devices={devices} layout={sidebarLayout} onLayoutChange={changeSidebarLayout} />
      )}
      <main className="content">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/about" element={<ProductPage />} />
          <Route path="/examples" element={<ExamplesPage />} />
          <Route path="/download" element={<DownloadPage />} />
          {/* 처음 들어오면: 로그인했으면 워크스페이스, 아니면 제품 소개 */}
          <Route path="/" element={authed ? <Navigate to="/services" replace /> : <ProductPage />} />
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
