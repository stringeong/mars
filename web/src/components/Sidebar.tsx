import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'
import { Device, Service } from '../types'
import AppIcon from './AppIcon'

const footerItems = [
  { to: '/history', label: '실행 이력', icon: 'history' as const },
  { to: '/files', label: '파일', icon: 'files' as const },
  { to: '/devices', label: '워커', icon: 'workers' as const },
  { to: '/marketplace', label: '마켓플레이스', icon: 'marketplace' as const },
  { to: '/settings', label: '설정', icon: 'settings' as const },
]

/** 대화형 앱처럼: 새 워크플로우 버튼, 워크플로우 목록, 아래쪽 메뉴 */
export default function Sidebar({ services, devices }: { services: Service[]; devices: Device[] }) {
  const location = useLocation()
  const navigate = useNavigate()
  const match = location.pathname.match(/^\/services\/(\d+)(?:\/(setup|run))?$/)
  const activeId = match ? Number(match[1]) : null
  const activeStep = match ? match[2] ?? 'builder' : null
  const online = devices.filter((device) => device.online).length

  async function duplicate(serviceId: number) {
    try {
      const copy = await api.post<Service>(`/services/${serviceId}/duplicate`)
      navigate(`/services/${copy.id}/setup`)
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '워크플로우를 복제하지 못했어요.')
    }
  }

  return <aside className="sidebar side">
    <Link to="/services" className="side-brand"><span className="brand-mark">M</span><strong>M.A.R.S</strong></Link>
    <Link to="/services" className={`side-new${location.pathname === '/services' ? ' active' : ''}`}>
      <span className="nav-icon"><AppIcon name="workflow" /></span><span>새 워크플로우</span>
    </Link>

    <div className="side-section"><span>워크플로우</span><Link to="/dashboard">모두 보기</Link></div>
    <nav className="side-list" aria-label="워크플로우 목록">
      {services.map((service) => <div key={service.id}>
        <Link to={`/services/${service.id}`} className={service.id === activeId ? 'active' : ''} title={service.name}>{service.name}</Link>
        {service.id === activeId && <div className="side-sublinks">
          <Link to={`/services/${service.id}/setup`} className={activeStep === 'setup' ? 'current' : ''}>설정 확인</Link>
          <Link to={`/services/${service.id}`} className={activeStep === 'builder' ? 'current' : ''}>편집</Link>
          <Link to={`/services/${service.id}/run`} className={activeStep === 'run' ? 'current' : ''}>실행</Link>
          <button type="button" onClick={() => duplicate(service.id)}>복제</button>
        </div>}
      </div>)}
      {!services.length && <small className="side-empty">만든 워크플로우가 여기에 쌓여요.</small>}
    </nav>

    <nav className="side-footer" aria-label="메뉴">
      {footerItems.map((item) => <Link key={item.to} to={item.to} className={location.pathname.startsWith(item.to) ? 'active' : ''}>
        <span className="nav-icon"><AppIcon name={item.icon} /></span>
        <span>{item.label}</span>
        {item.to === '/devices' && <small className={online ? 'side-online' : ''}>{online}/{devices.length} 온라인</small>}
      </Link>)}
      <button type="button" className="side-logout" onClick={() => { setToken(null); navigate('/login') }}>로그아웃</button>
    </nav>
  </aside>
}
