type IconName = 'dashboard' | 'workflow' | 'workers' | 'files' | 'history' | 'marketplace' | 'settings'

const paths: Record<IconName, JSX.Element> = {
  dashboard: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  workflow: <><circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M8 6h8M7.4 7.6l3.4 8M16.6 7.6l-3.4 8"/></>,
  workers: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 9h8M8 13h5M9 19v2M15 19v2"/></>,
  files: <><path d="M5 3h9l5 5v13H5z"/><path d="M14 3v5h5M8 13h8M8 17h6"/></>,
  history: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2M3 4v5h5"/></>,
  marketplace: <><path d="M4 9h16l-1 12H5zM3 9l2-6h14l2 6"/><path d="M8 9v2a2 2 0 0 0 4 0V9M12 9v2a2 2 0 0 0 4 0V9"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.1h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H3v-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V3h4v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.1v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
}

export default function AppIcon({ name }: { name: IconName }) {
  return <svg className="app-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}
