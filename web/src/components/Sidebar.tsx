import { KeyboardEvent, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'
import { Device, Service } from '../types'
import { announceServiceRenamed } from '../workflow'
import AppIcon from './AppIcon'

const footerItems = [
  { to: '/history', label: '실행 이력', icon: 'history' as const },
  { to: '/files', label: '파일', icon: 'files' as const },
  { to: '/devices', label: '워커', icon: 'workers' as const },
  { to: '/settings', label: '설정', icon: 'settings' as const },
]

/** 대화형 앱처럼: 새 워크플로우 버튼, 워크플로우 목록(이름 바꾸기 가능), 아래쪽 메뉴 */
export default function Sidebar({ services, devices }: { services: Service[]; devices: Device[] }) {
  const location = useLocation()
  const navigate = useNavigate()
  const match = location.pathname.match(/^\/services\/(\d+)(?:\/(setup|run))?$/)
  const activeId = match ? Number(match[1]) : null
  const activeStep = match ? match[2] ?? 'builder' : null
  const online = devices.filter((device) => device.online).length
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draftName, setDraftName] = useState('')
  // Enter로 저장한 뒤 입력칸이 사라지며 생기는 blur가 한 번 더 저장하지 않도록 막는다
  const finishingRef = useRef(false)

  function startRename(service: Service) {
    finishingRef.current = false
    setEditingId(service.id)
    setDraftName(service.name)
  }

  async function finishRename(service: Service, save: boolean) {
    if (finishingRef.current) return
    finishingRef.current = true
    setEditingId(null)
    const name = draftName.trim()
    if (!save || !name || name === service.name) return
    try {
      const updated = await api.put<Service>(`/services/${service.id}`, { name })
      announceServiceRenamed(updated.id, updated.name)
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '이름을 바꾸지 못했어요.')
    }
  }

  function onRenameKeyDown(event: KeyboardEvent<HTMLInputElement>, service: Service) {
    if (event.nativeEvent.isComposing) return
    if (event.key === 'Enter') { event.preventDefault(); finishRename(service, true) }
    if (event.key === 'Escape') { event.preventDefault(); finishRename(service, false) }
  }

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
      {services.map((service) => <div key={service.id} className={`side-item${service.id === activeId ? ' active' : ''}`}>
        {editingId === service.id
          ? <input
            className="side-rename"
            value={draftName}
            autoFocus
            maxLength={255}
            aria-label="워크플로우 이름"
            onFocus={(event) => event.currentTarget.select()}
            onChange={(event) => setDraftName(event.target.value)}
            onKeyDown={(event) => onRenameKeyDown(event, service)}
            onBlur={() => finishRename(service, true)}
          />
          : <>
            <Link
              to={`/services/${service.id}`}
              className={service.id === activeId ? 'active' : ''}
              title={`${service.name} (더블클릭해 이름 바꾸기)`}
              onDoubleClick={(event) => { event.preventDefault(); startRename(service) }}
            >{service.name}</Link>
            <button type="button" className="side-rename-button" aria-label={`${service.name} 이름 바꾸기`} title="이름 바꾸기" onClick={() => startRename(service)}>
              <AppIcon name="edit" />
            </button>
          </>}
        {service.id === activeId && editingId !== service.id && <div className="side-sublinks">
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
