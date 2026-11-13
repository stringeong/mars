import { KeyboardEvent, PointerEvent, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'
import { Device, ExecutionListItem, Service } from '../types'
import { announceServiceRenamed, deleteWorkflow, executionStatusLabel, sortDevices, timeAgo } from '../workflow'
import AppIcon from './AppIcon'

const footerItems = [
  { to: '/dashboard', label: '대시보드', icon: 'dashboard' as const },
  { to: '/history', label: '실행 이력', icon: 'history' as const },
  { to: '/files', label: '파일', icon: 'files' as const },
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

/** 메뉴형 사이드바: 새 워크플로우, 메뉴, 지금 열린 워크플로우, 내 워커 상태, 로그아웃. 접기와 폭 조절을 지원한다. */
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
  // 사이드바는 메뉴형: 워크플로우 목록은 대시보드에서 보고, 사이드바에는 지금 열린 워크플로우만 둔다
  const openService = services.find((service) => service.id === activeId)
  // 최근 실행 10개. 화면을 옮길 때마다 새로 불러온다. 완료는 점 없이, 실패·실행 중만 점으로 표시
  const [recentRuns, setRecentRuns] = useState<ExecutionListItem[]>([])
  useEffect(() => { api.get<ExecutionListItem[]>('/executions').then((list) => setRecentRuns(list.slice(0, 10))).catch(() => {}) }, [location.pathname])
  const activeStep = match ? match[2] ?? 'builder' : null
  const online = devices.filter((device) => device.online).length
  // 내 워커 칸: 사이드바에 남는 높이만큼 워커를 더 보여주고, 모자라면 줄인다.
  const asideRef = useRef<HTMLElement>(null)
  const spacerRef = useRef<HTMLDivElement>(null)
  // 내 워커 칸: 줄 수(높이)와 열 수(사이드바 너비)를 따로 정한다. 보여 줄 대수 = 줄 × 열
  const [workerRows, setWorkerRows] = useState(4)
  // 사이드바 폭(저장된 값)으로 열 수를 정한다. 드래그 중에는 바뀌지 않고, 놓는 순간 줄 수와 함께 한 번에 바뀌어 높이가 출렁이지 않는다
  const workerColumns = layout.width >= 274 ? 2 : 1
  const workerCount = Math.min(devices.length, workerRows * workerColumns)
  const [, setViewportTick] = useState(0)
  useEffect(() => {
    const onResize = () => setViewportTick((tick) => tick + 1)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  const [editingId, setEditingId] = useState<number | null>(null)
  const [openMenu, setOpenMenu] = useState(false)
  // 맨 아래 계정 메뉴: 제품 소개·커뮤니티·워커 다운로드·로그아웃
  const [accountOpen, setAccountOpen] = useState(false)
  const [me, setMe] = useState<{ username: string; email: string } | null>(null)
  const accountRef = useRef<HTMLDivElement>(null)
  useEffect(() => { api.get<{ username: string; email: string }>('/auth/me').then(setMe).catch(() => {}) }, [])
  useEffect(() => { setOpenMenu(false); setAccountOpen(false) }, [location.pathname])
  useEffect(() => {
    if (!accountOpen) return
    const close = (event: MouseEvent) => { if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [accountOpen])
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

  async function remove(service: Service) {
    if (await deleteWorkflow(service) && service.id === activeId) navigate('/services')
  }

  async function duplicate(serviceId: number) {
    try {
      const copy = await api.post<Service>(`/services/${serviceId}/duplicate`)
      navigate(`/services/${copy.id}/setup`)
    } catch (cause) {
      window.alert(cause instanceof Error ? cause.message : '워크플로우를 복제하지 못했어요.')
    }
  }

  useLayoutEffect(() => {
    const aside = asideRef.current
    const spacer = spacerRef.current
    if (!aside || !spacer || layout.collapsed || !devices.length) return
    const sample = aside.querySelector<HTMLElement>('.side-worker')
    const rowHeight = (sample?.offsetHeight ?? 26) + 2
    // 사이드바를 넓히면 두 줄(2열)로 보이므로 한 행에 들어가는 워커 수만큼 늘리고 줄인다.
    const columns = workerColumns
    // 공간이 모자라면 최근 실행 목록이 먼저 줄어들며 스크롤된다. 그만큼을 '넘친 높이'로 본다.
    const recent = aside.querySelector<HTMLElement>('.side-recent')
    const overflow = Math.max(aside.scrollHeight - aside.clientHeight, recent ? recent.scrollHeight - recent.clientHeight : 0)
    // 최근 실행과 내 워커 사이에 여백(약 28px)은 남겨 둔다.
    const gap = spacer.offsetHeight
    // 높이(줄 수)는 세로 공간으로만 정하고, 사이드바를 넓혀 2열이 되면 같은 높이에 두 배를 보여준다
    let nextRows = workerRows
    if (overflow > 0) nextRows = workerRows - Math.ceil(overflow / rowHeight)
    else if (gap < 20) nextRows = workerRows - 1
    else if (gap - 28 >= rowHeight && workerRows * columns < devices.length) nextRows = workerRows + Math.floor((gap - 28) / rowHeight)
    nextRows = Math.max(Math.min(3, Math.ceil(devices.length / columns)), Math.min(Math.ceil(devices.length / columns), nextRows))
    if (nextRows !== workerRows) setWorkerRows(nextRows)
  })

  return <aside ref={asideRef} className={`sidebar side${layout.collapsed ? ' collapsed' : ''}`}>
    <div className="side-head">
      <div className="side-brand">
        <Link to="/dashboard" className="side-brand-mark-link" aria-label="M.A.R.S 대시보드" title="대시보드"><span className="brand-mark">M</span></Link>
        <Link to="/dashboard" className="side-brand-name" title="대시보드"><strong>M.A.R.S</strong></Link>
      </div>
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

    <nav className="side-footer" aria-label="메뉴">
      {footerItems.map((item) => <Link key={item.to} to={item.to} title={item.label} className={location.pathname.startsWith(item.to) ? 'active' : ''}>
        <span className="nav-icon"><AppIcon name={item.icon} /></span>
        <span>{item.label}</span>
        {item.to === '/devices' && <small className={online ? 'side-online' : ''}>{online}/{devices.length} 온라인</small>}
      </Link>)}
    </nav>

    {openService && <section className="side-open" aria-label="열린 워크플로우">
      {editingId === openService.id
        ? <input
          className="side-rename"
          value={draftName}
          autoFocus
          maxLength={255}
          aria-label="워크플로우 이름"
          onFocus={(event) => event.currentTarget.select()}
          onChange={(event) => setDraftName(event.target.value)}
          onKeyDown={(event) => onRenameKeyDown(event, openService)}
          onBlur={() => finishRename(openService, true)}
        />
        : <div className="side-open-head">
          <strong title={`${openService.name} (더블클릭해 이름 바꾸기)`} onDoubleClick={() => startRename(openService)}>{openService.name}</strong>
          <button type="button" className="side-open-more" aria-label="워크플로우 메뉴" aria-expanded={openMenu} onClick={() => setOpenMenu((open) => !open)}><AppIcon name="more" /></button>
          {openMenu && <div className="side-open-menu" role="menu" onMouseLeave={() => setOpenMenu(false)}>
            <button type="button" role="menuitem" onClick={() => { setOpenMenu(false); startRename(openService) }}><AppIcon name="edit" />이름 바꾸기</button>
            <button type="button" role="menuitem" onClick={() => { setOpenMenu(false); duplicate(openService.id) }}><AppIcon name="copy" />복제</button>
            <button type="button" role="menuitem" className="danger" onClick={() => { setOpenMenu(false); remove(openService) }}><AppIcon name="trash" />삭제</button>
          </div>}
        </div>}
      <nav className="side-steps" aria-label="워크플로우 단계">
        <Link to={`/services/${openService.id}`} className={activeStep === 'builder' ? 'current' : ''}><AppIcon name="edit" />편집</Link>
        <Link to={`/services/${openService.id}/setup`} className={activeStep === 'setup' ? 'current' : ''}><AppIcon name="check" />설정 확인</Link>
        <Link to={`/services/${openService.id}/run`} className={activeStep === 'run' ? 'current' : ''}><AppIcon name="play" />실행</Link>
      </nav>
    </section>}

    {recentRuns.length > 0 && <>
    <div className="side-section side-recent-title"><span>최근 실행</span><Link to="/history">모두 보기</Link></div>
    <nav className="side-recent" aria-label="최근 실행">
      {recentRuns.map((run) => <Link key={run.id} to={`/executions/${run.id}`} className={`side-recent-item${location.pathname === `/executions/${run.id}` ? ' active' : ''}`} title={`${run.service_name} · ${executionStatusLabel(run.status)} · ${timeAgo(run.created_at)}`}>
        <span>{run.service_name}</span><i className={`side-run-dot ${run.status}`} aria-label={executionStatusLabel(run.status)} />
      </Link>)}
    </nav>
    </>}

    <div className="side-spacer" ref={spacerRef} />
    <Link to="/devices" className={`side-workers${location.pathname.startsWith('/devices') ? ' active' : ''}`} title={`워커 관리 · ${online}/${devices.length} 온라인`}>
      {/* 접었을 때는 같은 자리에 아이콘만 보인다 */}
      <span className="side-workers-icon nav-icon"><AppIcon name="workers" /></span>
      <span className="side-workers-head"><span>내 워커</span><b className={online ? 'side-online' : ''}>{online}/{devices.length} 온라인</b></span>
      {/* 상태는 로봇 색으로: 온라인은 초록, 오프라인은 회색(이름도 흐리게) */}
      {devices.length > 0 && <span className="side-workers-list" style={{ gridTemplateColumns: `repeat(${workerColumns}, minmax(0, 1fr))` }}>
        {sortDevices(devices).slice(0, workerCount).map((device) => <span key={device.id} className={`side-worker${device.online ? ' on' : ''}`} title={device.online ? '온라인' : '오프라인'}>
          <AppIcon name="workers" /><span>{device.name}</span>
        </span>)}
      </span>}
      {!devices.length && <span className="side-workers-empty">연결된 워커가 없어요 · 워커 연결하기 →</span>}
      {devices.length > workerCount && <span className="side-workers-more">+ {devices.length - workerCount}대 더 보기</span>}
    </Link>
    <div className="side-account" ref={accountRef}>
      {accountOpen && <div className="side-account-menu" role="menu">
        {me?.email && <small>{me.email}</small>}
        <Link to="/about" role="menuitem"><AppIcon name="info" />제품 소개</Link>
        <Link to="/examples" role="menuitem"><AppIcon name="users" />커뮤니티</Link>
        <Link to="/download" role="menuitem"><AppIcon name="download" />워커 다운로드</Link>
        <hr />
        <button type="button" role="menuitem" onClick={() => { setToken(null); navigate('/login') }}><AppIcon name="logout" />로그아웃</button>
      </div>}
      <button type="button" className="side-account-button" aria-haspopup="menu" aria-expanded={accountOpen} title="내 계정" onClick={() => setAccountOpen((open) => !open)}>
        <span className="side-avatar">{(me?.username ?? '?').slice(0, 1).toUpperCase()}</span>
        <span className="side-account-name">{me?.username ?? '내 계정'}</span>
        <AppIcon name="more" />
      </button>
    </div>
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
