type IconName = 'dashboard' | 'workflow' | 'workers' | 'files' | 'history' | 'marketplace'

const paths: Record<IconName, JSX.Element> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  workflow: <><circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M8 6h8M7.4 7.6l3.4 8M16.6 7.6l-3.4 8"/></>,
  workers: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 9h8M8 13h5M9 19v2M15 19v2"/></>,
  files: <><path d="M5 3h9l5 5v13H5z"/><path d="M14 3v5h5M8 13h8M8 17h6"/></>,
  history: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2M3 4v5h5"/></>,
  marketplace: <><path d="M4 9h16l-1 12H5zM3 9l2-6h14l2 6"/><path d="M8 9v2a2 2 0 0 0 4 0V9M12 9v2a2 2 0 0 0 4 0V9"/></>,
}

export default function AppIcon({ name }: { name: IconName }) {
  return <svg className="app-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}
