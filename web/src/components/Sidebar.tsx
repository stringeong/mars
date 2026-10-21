import { KeyboardEvent, PointerEvent, useRef, useState } from 'react'
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

// 사이드바 폭 (px). 접으면 아이콘만 보이는 폭으로 줄어든다.
export const SIDEBAR_DEFAULT_WIDTH = 224
export const SIDEBAR_COLLAPSED_WIDTH = 64
const SIDEBAR_MIN_WIDTH = 180
const SIDEBAR_MAX_WIDTH = 400
const SIDEBAR_STORAGE_KEY = 'mars_sidebar'

export type SidebarLayout = { width: number; collapsed: boolean }

const clampWidth = (value: number) => Math.round(Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, value)))

/** 브라우저에 저장한 폭·접힘 상태. 저장소를 못 쓰면 기본값으로 시작한다. */
export function loadSidebarLayout(): SidebarLayout {
  try {
    const saved = JSON.parse(localStorage.getItem(SIDEBAR_STORAGE_KEY) ?? 'null')
    if (saved && typeof saved.width === 'number') return { width: clampWidth(saved.width), collapsed: !!saved.collapsed }
  } catch {
    // 저장소를 쓸 수 없으면 기본값을 쓴다
  }
  return { width: SIDEBAR_DEFAULT_WIDTH, collapsed: false }
}

export function saveSidebarLayout(layout: SidebarLayout) {
  try {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, JSON.stringify(layout))
  } catch {
    // 저장하지 못해도 이번 화면에서는 그대로 쓴다
  }
}

/** 대화형 앱처럼: 새 워크플로우 버튼, 워크플로우 목록(이름 바꾸기 가능), 아래쪽 메뉴. 접기와 폭 조절을 지원한다. */
export default function Sidebar({ services, devices, layout, onLayoutChange }: {
  services: Service[]
  devices: Device[]
  layout: SidebarLayout
  onLayoutChange: (layout: SidebarLayout) => void
}) {
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

  // 드래그하는 동안에는 CSS 변수만 바꿔 화면 전체를 다시 그리지 않고, 놓을 때 폭을 저장한다
  function startResize(event: PointerEvent<HTMLDivElement>) {
    event.preventDefault()
    const handle = event.currentTarget
    const shell = handle.closest<HTMLElement>('.layout')
    let width = layout.width
    handle.setPointerCapture(event.pointerId)
    document.body.classList.add('resizing-sidebar')
    const move = (moveEvent: globalThis.PointerEvent) => {
      width = clampWidth(moveEvent.clientX)
      shell?.style.setProperty('--sidebar-width', `${width}px`)
    }
    const end = () => {
      handle.removeEventListener('pointermove', move)
      handle.removeEventListener('pointerup', end)
      handle.removeEventListener('pointercancel', end)
      document.body.classList.remove('resizing-sidebar')
      onLayoutChange({ width, collapsed: false })
    }
    handle.addEventListener('pointermove', move)
    handle.addEventListener('pointerup', end)
    handle.addEventListener('pointercancel', end)
  }

  function onResizeKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 48 : 16
    if (event.key === 'ArrowLeft') { event.preventDefault(); onLayoutChange({ width: clampWidth(layout.width - step), collapsed: false }) }
    if (event.key === 'ArrowRight') { event.preventDefault(); onLayoutChange({ width: clampWidth(layout.width + step), collapsed: false }) }
    if (event.key === 'Enter') { event.preventDefault(); onLayoutChange({ width: SIDEBAR_DEFAULT_WIDTH, collapsed: false }) }
  }

  async function duplicate(serviceId: number) {
    try {
      const copy = await api.post<Service>(`/services/${serviceId}/duplicate`)
      navigate(`/services/${copy.id}/setup`)
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '워크플로우를 복제하지 못했어요.')
    }
  }

  return <aside className={`sidebar side${layout.collapsed ? ' collapsed' : ''}`}>
    <div className="side-head">
      <Link to="/services" className="side-brand" title="M.A.R.S"><span className="brand-mark">M</span><strong>M.A.R.S</strong></Link>
      <button
        type="button"
        className="side-toggle"
        aria-label={layout.collapsed ? '사이드바 펼치기' : '사이드바 접기'}
        aria-expanded={!layout.collapsed}
        title={layout.collapsed ? '사이드바 펼치기' : '사이드바 접기'}
        onClick={() => onLayoutChange({ ...layout, collapsed: !layout.collapsed })}
      ><AppIcon name="panel" /></button>
    </div>
    <Link to="/services" title="새 워크플로우" className={`side-new${location.pathname === '/services' ? ' active' : ''}`}>
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
      {footerItems.map((item) => <Link key={item.to} to={item.to} title={item.label} className={location.pathname.startsWith(item.to) ? 'active' : ''}>
        <span className="nav-icon"><AppIcon name={item.icon} /></span>
        <span>{item.label}</span>
        {item.to === '/devices' && <small className={online ? 'side-online' : ''}>{online}/{devices.length} 온라인</small>}
      </Link>)}
      <button type="button" className="side-logout" onClick={() => { setToken(null); navigate('/login') }}>로그아웃</button>
    </nav>
    {!layout.collapsed && <div
      className="side-resizer"
      role="separator"
      aria-orientation="vertical"
      aria-label="사이드바 너비 조절 (좌우 화살표, Enter로 기본 폭)"
      aria-valuemin={SIDEBAR_MIN_WIDTH}
      aria-valuemax={SIDEBAR_MAX_WIDTH}
      aria-valuenow={layout.width}
      tabIndex={0}
      title="끌어서 너비 조절 · 더블클릭하면 기본 폭"
      onPointerDown={startResize}
      onKeyDown={onResizeKeyDown}
      onDoubleClick={() => onLayoutChange({ width: SIDEBAR_DEFAULT_WIDTH, collapsed: false })}
    />}
  </aside>
}
